from __future__ import annotations

import logging
from typing import Any

from app.config import Settings
from utils.runtime_state_store import load_latest_runtime_snapshot
from utils.structured_log import log_event

logger = logging.getLogger(__name__)

_HINT_REASONS = frozenset(
    {
        "pipeline_inner_failed",
        "pipeline_outer_failed",
        "critical_runtime_failure",
    }
)


def log_startup_recovery_hints_if_any(settings: Settings) -> None:
    """
    If a recent failure snapshot exists, emit structured hints (no auto-remediation).
    """
    try:
        data = load_latest_runtime_snapshot(settings)
    except Exception as exc:
        log_event(logger, "startup.recovery_hint_load_failed", error=repr(exc), recovery="ignored")
        return

    if not data:
        return

    reason = str(data.get("reason") or "")
    if reason not in _HINT_REASONS:
        return

    dump = data.get("diagnostics_dump") or {}
    rs = dump.get("runtime_snapshot") or data.get("runtime_snapshot") or {}
    sched = rs.get("scheduler") or data.get("scheduler_state") or {}
    errs = data.get("recent_errors") or []

    last_uptime = None
    if isinstance(rs, dict):
        last_uptime = rs.get("uptime_sec")

    log_event(
        logger,
        "startup.recovery_hint",
        last_snapshot_reason=reason,
        recorded_at_iso=str(data.get("recorded_at_iso") or ""),
        last_uptime_sec=last_uptime,
        last_scheduler_state=_safe_jsonable(sched),
        recent_error_count=len(errs) if isinstance(errs, list) else 0,
        recent_error_preview=_preview_errors(errs),
        hint="Review latest snapshot via admin CLI: python tools/admin_cli.py latest-snapshot --json",
    )


def _safe_jsonable(o: Any) -> Any:
    if isinstance(o, dict):
        return {str(k): o[k] for k in list(o.keys())[:24]}
    return o


def _preview_errors(errs: Any, *, limit: int = 3) -> list[dict[str, Any]]:
    if not isinstance(errs, list):
        return []
    out: list[dict[str, Any]] = []
    for e in errs[:limit]:
        if isinstance(e, dict):
            out.append(
                {
                    "kind": e.get("kind"),
                    "message": (str(e.get("message") or ""))[:200],
                }
            )
    return out
