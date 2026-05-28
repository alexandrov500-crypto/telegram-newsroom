"""Public launch traffic metrics (local-only, no external analytics)."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from utils.structured_log import log_event

import logging

logger = logging.getLogger(__name__)


def _metrics_path(runtime_dir: str) -> Path:
    return Path(runtime_dir).expanduser().resolve() / "public_traffic_metrics.jsonl"


def _count_recent_alerts(runtime_dir: str, hours: int) -> int:
    p = Path(runtime_dir).expanduser().resolve() / "ops" / "pending_notifications.jsonl"
    if not p.is_file():
        return 0
    cutoff = time.time() - (hours * 3600.0)
    out = 0
    for ln in p.read_text(encoding="utf-8", errors="replace").splitlines()[-500:]:
        try:
            row = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if float(row.get("ts_unix") or 0) >= cutoff:
            out += 1
    return out


def _subscriber_growth_proxy(conn: sqlite3.Connection, hours: int) -> int:
    # No direct subscriber API -> proxy using first-time source-channel appearances in published drafts.
    q = """
    WITH src AS (
      SELECT d.id, pp.published_at, json_extract(value, '$.channel') AS channel
      FROM published_posts pp
      JOIN drafts d ON d.id = pp.draft_id, json_each(d.sources)
      WHERE pp.published_at >= datetime('now', ?)
    )
    SELECT COUNT(DISTINCT channel) FROM src WHERE channel IS NOT NULL AND channel != ''
    """
    try:
        row = conn.execute(q, (f"-{hours} hours",)).fetchone()
        return int((row or [0])[0] or 0)
    except sqlite3.OperationalError:
        return 0


def _delivery_cadence_min(conn: sqlite3.Connection, hours: int) -> float | None:
    q = """
    SELECT CAST((julianday(MAX(published_at)) - julianday(MIN(published_at))) * 24.0 * 60.0 AS REAL), COUNT(*)
    FROM published_posts
    WHERE published_at >= datetime('now', ?)
    """
    row = conn.execute(q, (f"-{hours} hours",)).fetchone()
    span_min, n = row or (None, 0)
    if not n or int(n) < 2 or span_min is None:
        return None
    return round(float(span_min) / max(1, int(n) - 1), 2)


def _publish_frequency_stability(conn: sqlite3.Connection, hours: int) -> float:
    q = """
    SELECT strftime('%Y-%m-%dT%H', published_at) AS hour_bucket, COUNT(*) AS c
    FROM published_posts
    WHERE published_at >= datetime('now', ?)
    GROUP BY hour_bucket
    ORDER BY hour_bucket ASC
    """
    rows = conn.execute(q, (f"-{hours} hours",)).fetchall()
    vals = [int(r[1] or 0) for r in rows]
    if len(vals) < 2:
        return 1.0
    mean = sum(vals) / len(vals)
    if mean <= 0:
        return 0.0
    var = sum((x - mean) ** 2 for x in vals) / len(vals)
    cv = (var**0.5) / mean
    return round(max(0.0, 1.0 - min(1.0, cv)), 4)


def build_public_traffic_snapshot(conn: sqlite3.Connection, *, runtime_dir: str) -> dict[str, Any]:
    from app.observability.publish_continuity import compute_autonomous_continuity_score
    from app.observability.telegram_production import production_validation_report
    from app.ops.live_rollback import rollback_active
    from app.ops.public_incident_safety import incident_frozen

    continuity = compute_autonomous_continuity_score(conn, runtime_dir=runtime_dir)
    tg = production_validation_report()
    windows = {}
    for label, h in (("1h", 1), ("24h", 24), ("7d", 24 * 7)):
        pub = conn.execute(
            "SELECT COUNT(*) FROM published_posts WHERE published_at >= datetime('now', ?)",
            (f"-{h} hours",),
        ).fetchone()
        windows[label] = {
            "publishes": int((pub or [0])[0] or 0),
            "avg_cadence_min": _delivery_cadence_min(conn, h),
            "frequency_stability": _publish_frequency_stability(conn, h),
            "subscriber_growth_proxy": _subscriber_growth_proxy(conn, h),
            "alert_frequency": _count_recent_alerts(runtime_dir, h),
        }
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "continuity_score": continuity.get("autonomous_continuity_score"),
        "post_delivery_cadence_min_24h": windows["24h"]["avg_cadence_min"],
        "publish_frequency_stability_24h": windows["24h"]["frequency_stability"],
        "telegram_api_health_ok": bool(tg.get("ok")),
        "engagement_proxy": {
            "publish_count_24h": windows["24h"]["publishes"],
            "cadence_consistency_24h": windows["24h"]["frequency_stability"],
        },
        "operator_intervention_frequency": windows["24h"]["alert_frequency"],
        "rollback_incidents": 1 if rollback_active(runtime_dir) else 0,
        "autopublish_freezes": 1 if incident_frozen(runtime_dir) else 0,
        "windows": windows,
    }


def append_public_traffic_snapshot(runtime_dir: str, snapshot: dict[str, Any]) -> Path:
    path = _metrics_path(runtime_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(snapshot, ensure_ascii=False, default=str) + "\n")
    return path


async def run_public_traffic_heartbeat(settings: Any) -> dict[str, Any]:
    from utils.database_url import sqlite_path_from_url

    raw = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/newsroom.db").strip()
    db_path = sqlite_path_from_url(raw)
    if not db_path or not Path(db_path).is_file():
        return {"skipped": True, "reason": "db_unavailable"}
    conn = sqlite3.connect(db_path, timeout=5.0)
    try:
        snap = build_public_traffic_snapshot(conn, runtime_dir=settings.runtime_state_dir)
    finally:
        conn.close()
    out = append_public_traffic_snapshot(settings.runtime_state_dir, snap)
    log_event(logger, "public_traffic_monitor.heartbeat", path=str(out), continuity=snap.get("continuity_score"))
    return snap
