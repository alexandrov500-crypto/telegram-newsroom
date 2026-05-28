"""Autonomous operations runtime report (read-only JSON snapshot)."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.observability.burnin_eval import publishability_metrics, scan_log_contract
from app.observability.stability_metrics import compute_system_stability_score
from app.observability.ops_health import gather_component_health


def _uptime_sec() -> float | None:
    started = os.getenv("RUNTIME_STARTED_UNIX", "").strip()
    if started:
        try:
            return max(0.0, time.time() - float(started))
        except ValueError:
            pass
    return None


def build_runtime_report(settings: Any | None = None) -> dict[str, Any]:
    import sqlite3
    from utils.database_url import sqlite_path_from_url

    raw = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/newsroom.db").strip()
    path = sqlite_path_from_url(raw)
    conn = None
    ticks: list[dict[str, Any]] = []
    pub_metrics: dict[str, Any] = {}
    stability: dict[str, Any] = {}
    if path and Path(path).is_file():
        conn = sqlite3.connect(path, timeout=3.0)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT id, status,
                   json_extract(detail_json, '$.terminal_state') AS terminal_state,
                   json_extract(detail_json, '$.draft_id') AS draft_id,
                   json_extract(detail_json, '$.terminal_reason') AS reason,
                   datetime(finished_at) AS finished_at
            FROM pipeline_ticks
            WHERE finished_at IS NOT NULL
            ORDER BY id DESC LIMIT 20
            """
        ).fetchall()
        ticks = [dict(r) for r in rows]
        pub_metrics = publishability_metrics(conn)
        media_rate = conn.execute(
            """
            SELECT COUNT(*) FROM drafts
            WHERE extras LIKE '%"media_status"%'
              AND extras NOT LIKE '%"media_status": "failed"%'
              AND created_at >= datetime('now', '-24 hours')
            """
        ).fetchone()
        drafts_24 = conn.execute(
            "SELECT COUNT(*) FROM drafts WHERE created_at >= datetime('now', '-24 hours')"
        ).fetchone()
        publishes_24 = conn.execute(
            "SELECT COUNT(*) FROM published_posts WHERE published_at >= datetime('now', '-24 hours')"
        ).fetchone()
        pub_metrics["drafts_created_24h"] = int(drafts_24[0] if drafts_24 else 0)
        pub_metrics["publishes_24h"] = int(publishes_24[0] if publishes_24 else 0)
        pub_metrics["media_attach_rate_24h"] = round(
            int(media_rate[0] if media_rate else 0) / max(1, int(drafts_24[0] if drafts_24 else 1)),
            3,
        )
        stability = compute_system_stability_score(conn)
        conn.close()
    log_path = Path(os.getenv("NEWSROOM_LOG", "logs/local-run.log"))
    log_contract = scan_log_contract(log_path) if log_path.is_file() else {"available": False}
    health = gather_component_health(settings)
    from app.editorial.burnin_governance import governance_snapshot
    from app.ops.runtime_control import runtime_control_payload

    runtime_dir = getattr(settings, "runtime_state_dir", None) or os.getenv("RUNTIME_STATE_DIR", "var/runtime")
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "uptime_sec": _uptime_sec(),
        "health": health,
        "last_ticks": ticks,
        "publishability": pub_metrics,
        "stability": stability,
        "runtime_control": runtime_control_payload(str(runtime_dir)),
        "log_contract": log_contract,
        "governance": governance_snapshot(),
        "fallback_tier": _infer_fallback_tier(log_contract, health),
    }


def _infer_fallback_tier(log_contract: dict[str, Any], health: dict[str, Any]) -> str:
    if int(log_contract.get("rule_fallback") or 0) > 0:
        return "rule_fallback_starvation"
    openai = health.get("openai") or {}
    if openai.get("degraded"):
        return "openai_degraded"
    return "primary"


def write_runtime_report(settings: Any | None = None, *, out_path: Path | None = None) -> Path:
    runtime_dir = Path(
        getattr(settings, "runtime_state_dir", None) or os.getenv("RUNTIME_STATE_DIR", "var/runtime")
    )
    dest = out_path or (runtime_dir / "runtime_report.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = build_runtime_report(settings)
    dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
    return dest
