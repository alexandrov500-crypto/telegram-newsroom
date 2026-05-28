"""Burn-in soft governance and output starvation signals (env-driven, observable)."""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

from utils.database_url import sqlite_path_from_url
from utils.structured_log import log_event

logger = __import__("logging").getLogger(__name__)


def _env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float, *, lo: float, hi: float) -> float:
    raw = os.getenv(name, str(default)).strip()
    try:
        return max(lo, min(hi, float(raw)))
    except ValueError:
        return default


def burnin_soft_governance_enabled() -> bool:
    return _env_bool("BURNIN_SOFT_GOVERNANCE", "false")


def source_cooldown_sec() -> float:
    minutes = _env_float(
        "SOURCE_COOLDOWN_MINUTES",
        3.0 if burnin_soft_governance_enabled() else 15.0,
        lo=0.5,
        hi=120.0,
    )
    return minutes * 60.0


def cluster_suppress_strict() -> bool:
    if burnin_soft_governance_enabled():
        return _env_bool("CLUSTER_SUPPRESS_STRICT", "false")
    return _env_bool("CLUSTER_SUPPRESS_STRICT", "true")


def duplicate_strict_mode() -> bool:
    if burnin_soft_governance_enabled():
        return _env_bool("DUPLICATE_STRICT_MODE", "false")
    return _env_bool("DUPLICATE_STRICT_MODE", "true")


def min_drafts_per_24h_target() -> int:
    return int(
        _env_float("MIN_DRAFTS_PER_24H_TARGET", 1.0 if burnin_soft_governance_enabled() else 0.0, lo=0.0, hi=48.0)
    )


def burnin_openai_always_fallback() -> bool:
    """During burn-in, use rule fallback on OpenAI errors even without desk starvation."""
    return _env_bool("BURNIN_OPENAI_ALWAYS_FALLBACK", "false") or burnin_soft_governance_enabled()


def governance_snapshot() -> dict[str, Any]:
    return {
        "burnin_soft_governance": burnin_soft_governance_enabled(),
        "source_cooldown_sec": source_cooldown_sec(),
        "cluster_suppress_strict": cluster_suppress_strict(),
        "duplicate_strict_mode": duplicate_strict_mode(),
        "min_drafts_per_24h_target": min_drafts_per_24h_target(),
        "burnin_openai_always_fallback": burnin_openai_always_fallback(),
    }


def _sqlite_path() -> str | None:
    raw = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/newsroom.db").strip()
    path = sqlite_path_from_url(raw)
    return str(path) if path else None


def committed_drafts_last_hours(hours: float = 24.0) -> int:
    db = _sqlite_path()
    if not db:
        return 0
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=max(1.0, hours))).isoformat()
    try:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2.0)
    except Exception:
        conn = sqlite3.connect(db, timeout=2.0)
    try:
        row = conn.execute(
            """
            SELECT COUNT(*) FROM pipeline_ticks
            WHERE finished_at IS NOT NULL
              AND finished_at >= ?
              AND json_extract(detail_json, '$.terminal_state') = 'committed_draft'
            """,
            (cutoff,),
        ).fetchone()
        return int(row[0] if row else 0)
    except Exception:
        return 0
    finally:
        conn.close()


def check_output_starvation(settings: Any) -> dict[str, Any]:
    """
    Emit pipeline.starvation_detected when no committed_draft in window.
    Does not change pipeline logic — observability + operator signal.
    """
    hours = _env_float("BURNIN_STARVATION_HOURS", 12.0, lo=1.0, hi=72.0)
    drafts = committed_drafts_last_hours(hours)
    target = min_drafts_per_24h_target()
    starving = target > 0 and drafts < target
    snap = {
        "hours_window": hours,
        "committed_drafts": drafts,
        "min_target": target,
        "starving": starving,
        **governance_snapshot(),
    }
    if starving:
        log_event(
            logger,
            "pipeline.starvation_detected",
            committed_drafts=drafts,
            hours_window=hours,
            min_target=target,
            recovery="enable_BURNIN_SOFT_GOVERNANCE_or_restore_OpenAI_quota",
        )
        try:
            from ops.operator_notifications import enqueue_operator_notification

            enqueue_operator_notification(
                settings.runtime_state_dir,
                kind="pipeline_output_starvation",
                severity="high",
                message=f"No committed_draft in {hours:.0f}h (count={drafts}, target>={target})",
                fields=snap,
            )
        except Exception:
            pass
    return snap
