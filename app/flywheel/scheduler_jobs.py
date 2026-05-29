"""W3 maintenance jobs — memory compression + cohort refresh."""

from __future__ import annotations

import logging

from app.flywheel.cohort_segmentation import refresh_cohort_memory
from app.flywheel.memory_compression import compress_style_memory
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


async def run_flywheel_maintenance_tick(ctx: object) -> dict[str, object]:
    settings = ctx.settings  # type: ignore[attr-defined]
    runtime_dir = settings.runtime_state_dir
    result: dict[str, object] = {}
    try:
        result["cohorts"] = await refresh_cohort_memory(runtime_dir)
    except Exception as exc:
        log_event(logger, "flywheel.cohort_refresh_failed", error=repr(exc)[:200])
    try:
        result["compression"] = await compress_style_memory()
    except Exception as exc:
        log_event(logger, "flywheel.compression_failed", error=repr(exc)[:200])
    log_event(logger, "flywheel.maintenance_complete", keys=list(result.keys()))
    return result
