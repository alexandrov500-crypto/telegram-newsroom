"""SLO metrics for editorial stability."""

from __future__ import annotations

import json
import sqlite3
import time
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

from app.editorial.desk_starvation import hours_since_last_publish
from app.editorial.stability.anti_pause import evaluate_anti_pause
from app.editorial.stability.config import (
    anti_pause_max_gap_minutes,
    baseline_posts_per_day,
    contextual_post_min_ratio_pct,
    stability_layer_enabled,
    target_posts_per_day,
)
from app.editorial.stability.state import load_state
from utils.database_url import sqlite_path_from_url


def _db_path() -> str | None:
    import os

    raw = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/newsroom.db").strip()
    p = sqlite_path_from_url(raw)
    return str(p) if p else None


def _posts_today() -> int:
    db = _db_path()
    if not db:
        return 0
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2.0)
        row = conn.execute(
            "SELECT COUNT(*) FROM published_posts WHERE published_at >= ?",
            (cutoff,),
        ).fetchone()
        conn.close()
        return int(row[0] if row else 0)
    except Exception:
        return 0


def _contextual_ratio_pct(runtime_dir: str | None) -> float:
    data = load_state(runtime_dir)
    day_key = datetime.now(UTC).strftime("%Y-%m-%d")
    day = (data.get("daily_stats") or {}).get(day_key) or {}
    total = int(day.get("posts") or 0)
    contextual = int(day.get("contextual_posts") or 0)
    if total <= 0:
        return 0.0
    return round(contextual / total * 100.0, 1)


def record_stability_publish(
    runtime_dir: str | None,
    *,
    post_type: str,
    publishing_mode: str = "core",
) -> None:
    from app.editorial.stability.state import load_state, save_state

    data = load_state(runtime_dir)
    day_key = datetime.now(UTC).strftime("%Y-%m-%d")
    days = dict(data.get("daily_stats") or {})
    day = dict(days.get(day_key) or {})
    day["posts"] = int(day.get("posts") or 0) + 1
    contextual_types = {"context", "digest", "explainer"}
    if post_type in contextual_types or publishing_mode != "core":
        day["contextual_posts"] = int(day.get("contextual_posts") or 0) + 1
    day["last_publish_ts"] = time.time()
    days[day_key] = day
    data["daily_stats"] = days
    save_state(runtime_dir, data)


def continuity_score(anti_pause_reason: str, gap_minutes: float | None) -> float:
    max_gap = float(anti_pause_max_gap_minutes())
    if gap_minutes is None:
        return 0.0
    if gap_minutes <= max_gap * 0.5:
        return 1.0
    if gap_minutes <= max_gap:
        return round(1.0 - (gap_minutes - max_gap * 0.5) / (max_gap * 0.5), 3)
    return 0.0


def stability_slo_snapshot(runtime_dir: str | None = None, *, newsroom_tz: str = "Europe/Moscow") -> dict[str, Any]:
    ap = evaluate_anti_pause(newsroom_tz=newsroom_tz)
    posts_24h = _posts_today()
    ctx_ratio = _contextual_ratio_pct(runtime_dir)
    gap = ap.publish_gap_minutes
    score = continuity_score(ap.reason, gap)

    slo = {
        "publish_gap_minutes": gap,
        "max_gap_minutes_slo": anti_pause_max_gap_minutes(),
        "gap_slo_ok": gap is None or gap <= anti_pause_max_gap_minutes(),
        "posts_last_24h": posts_24h,
        "baseline_posts_per_day": baseline_posts_per_day(),
        "target_posts_per_day": target_posts_per_day(),
        "baseline_slo_ok": posts_24h >= baseline_posts_per_day(),
        "contextual_ratio_pct": ctx_ratio,
        "contextual_min_pct": contextual_post_min_ratio_pct(),
        "contextual_slo_ok": ctx_ratio >= contextual_post_min_ratio_pct() or posts_24h < 3,
        "continuity_score": score,
        "silence_events_24h": len(
            [
                e
                for e in (load_state(runtime_dir).get("silence_events") or [])
                if isinstance(e, dict)
            ]
        ),
    }
    return {
        "enabled": stability_layer_enabled(),
        "anti_pause": ap.to_dict(),
        "slo": slo,
        "overall_ok": slo["gap_slo_ok"] and slo["baseline_slo_ok"],
    }
