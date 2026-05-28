"""Pipeline watchdog — detect stuck stages and trigger safe step recovery."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from utils.metrics import inc
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


def _stage_stuck_sec() -> float:
    try:
        return max(300.0, float(os.getenv("PIPELINE_STAGE_STUCK_SEC", "900")))
    except ValueError:
        return 900.0


async def run_pipeline_watchdog(settings: Any, *, collector_enabled: bool = True) -> dict[str, Any]:
    """
    Safe recovery only:
    - mark stale pipeline ticks (existing)
    - enqueue failed-draft retry batch (transient publish failures)
    Does NOT restart the process.
    """
    out: dict[str, Any] = {"ts": time.time(), "stage_stuck_sec": _stage_stuck_sec()}
    tick_result: dict[str, Any] = {}

    try:
        from app.reliability.pipeline_ticks import check_stuck_pipeline_ticks

        tick_result = await check_stuck_pipeline_ticks(settings)
        out["pipeline_ticks"] = tick_result
        if tick_result.get("stale_marked"):
            inc("pipeline_watchdog_stale_recovered")
    except Exception as exc:
        out["pipeline_ticks_error"] = repr(exc)[:200]
        log_event(logger, "pipeline_watchdog.tick_check_failed", error=repr(exc)[:200])

    if tick_result.get("stale_marked"):
        out["recovery"] = "stale_ticks_marked_safe_retry_via_heartbeat"
        log_event(
            logger,
            "pipeline_watchdog.recovery_hint",
            action="failed_draft_retry_batch_on_next_heartbeat",
            stale_count=len(tick_result.get("stale_marked") or []),
        )

    log_event(logger, "pipeline_watchdog.completed", **{k: v for k, v in out.items() if k != "ts"})
    return out
