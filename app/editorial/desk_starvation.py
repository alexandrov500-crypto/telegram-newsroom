"""Publish starvation detection and adaptive desk thresholds (no bypass of hard rejects)."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from utils.database_url import sqlite_path_from_url


def _env_float(name: str, default: float, *, lo: float, hi: float) -> float:
    raw = os.getenv(name, str(default)).strip()
    try:
        return max(lo, min(hi, float(raw)))
    except ValueError:
        return default


def _sqlite_db_path() -> str | None:
    raw = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/newsroom.db").strip()
    path = sqlite_path_from_url(raw)
    return str(path) if path is not None else None


def last_publish_at_sync() -> datetime | None:
    db_path = _sqlite_db_path()
    if not db_path:
        return None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2.0)
    except Exception:
        try:
            conn = sqlite3.connect(db_path, timeout=2.0)
        except Exception:
            return None
    try:
        row = conn.execute(
            "SELECT published_at FROM published_posts ORDER BY id DESC LIMIT 1"
        ).fetchone()
    except Exception:
        return None
    finally:
        conn.close()
    if not row or not row[0]:
        return None
    try:
        dt = datetime.fromisoformat(str(row[0]).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def hours_since_last_publish() -> float | None:
    ts = last_publish_at_sync()
    if ts is None:
        return None
    return max(0.0, (datetime.now(timezone.utc) - ts.astimezone(timezone.utc)).total_seconds() / 3600.0)


@dataclass(frozen=True)
class DeskThresholdContext:
    base_min_publish_score: float
    effective_min_publish_score: float
    lower_priority_score: float
    min_macro_market_score: float
    relevance_floor: float
    starvation_active: bool
    publish_starvation_detected: bool
    hours_since_publish: float | None
    score_reduction: float


def desk_threshold_context() -> DeskThresholdContext:
    base_min = _env_float("DESK_MIN_QUALITY_SCORE", 45.0, lo=30.0, hi=80.0)
    lower = _env_float("DESK_LOWER_PRIORITY_SCORE", 32.0, lo=20.0, hi=60.0)
    macro_floor = _env_float("DESK_MIN_MACRO_MARKET_SCORE", 30.0, lo=20.0, hi=50.0)
    starvation_hours = _env_float("DESK_STARVATION_HOURS", 6.0, lo=1.0, hi=72.0)
    max_reduction = _env_float("DESK_STARVATION_MAX_SCORE_REDUCTION", 8.0, lo=0.0, hi=20.0)
    score_floor = _env_float("DESK_STARVATION_MIN_SCORE_FLOOR", 38.0, lo=28.0, hi=55.0)
    rel_normal = _env_float("DESK_RELEVANCE_FLOOR", 0.28, lo=0.15, hi=0.5)
    rel_starvation = _env_float("DESK_STARVATION_RELEVANCE_FLOOR", 0.22, lo=0.15, hi=0.4)

    hours = hours_since_last_publish()
    never_published = hours is None
    starvation_detected = never_published or (hours is not None and hours >= starvation_hours)

    reduction = 0.0
    if starvation_detected:
        if never_published:
            excess_hours = starvation_hours + 6.0
        else:
            assert hours is not None
            excess_hours = max(0.0, hours - starvation_hours)
        reduction = min(max_reduction, excess_hours * 0.5)

    effective_min = max(score_floor, base_min - reduction)
    effective_min = max(lower + 1.0, effective_min)
    relevance_floor = rel_starvation if starvation_detected else rel_normal

    return DeskThresholdContext(
        base_min_publish_score=base_min,
        effective_min_publish_score=round(effective_min, 2),
        lower_priority_score=lower,
        min_macro_market_score=macro_floor,
        relevance_floor=relevance_floor,
        starvation_active=starvation_detected and reduction > 0,
        publish_starvation_detected=starvation_detected,
        hours_since_publish=round(hours, 2) if hours is not None else None,
        score_reduction=round(reduction, 2),
    )


def record_desk_decision(
    runtime_dir: str | None,
    *,
    publish: bool,
    reason: str,
    quality_score: float,
    threshold_ctx: DeskThresholdContext,
) -> None:
    """Append last-tick desk stats for /health (sync, best-effort)."""
    try:
        from ops.pipeline.paths import runtime_root

        path = runtime_root(runtime_dir) / "desk_last_tick.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        prev: dict[str, Any] = {}
        if path.is_file():
            try:
                prev = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                prev = {}
        breakdown = dict(prev.get("rejection_reason_breakdown") or {})
        if not publish:
            breakdown[reason] = int(breakdown.get(reason) or 0) + 1
        payload = {
            "updated_unix": time.time(),
            "rejected_last_tick": int(not publish),
            "last_reason": reason,
            "last_quality_score": quality_score,
            "rejection_reason_breakdown": breakdown,
            "threshold": threshold_ctx.effective_min_publish_score,
            "starvation_active": threshold_ctx.starvation_active,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def desk_health_snapshot() -> dict[str, Any]:
    ctx = desk_threshold_context()
    last_at = last_publish_at_sync()
    last_tick: dict[str, Any] = {}
    try:
        from ops.pipeline.paths import runtime_root

        path = runtime_root(None) / "desk_last_tick.json"
        if path.is_file():
            last_tick = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    out: dict[str, Any] = {
        "last_publish_at": last_at.isoformat() if last_at else None,
        "hours_since_publish": ctx.hours_since_publish,
        "current_threshold": ctx.effective_min_publish_score,
        "base_threshold": ctx.base_min_publish_score,
        "relevance_floor": ctx.relevance_floor,
        "rejected_last_tick": int(last_tick.get("rejected_last_tick") or 0),
        "rejection_reason_breakdown": last_tick.get("rejection_reason_breakdown") or {},
        "last_desk_reason": last_tick.get("last_reason"),
        "last_quality_score": last_tick.get("last_quality_score"),
        "publish_starvation_detected": ctx.publish_starvation_detected,
        "starvation_recovery_active": ctx.starvation_active,
        "score_reduction": ctx.score_reduction,
    }
    return out
