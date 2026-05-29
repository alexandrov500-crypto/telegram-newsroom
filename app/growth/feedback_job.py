"""Orchestrates growth feedback refresh (analytics tick hook)."""

from __future__ import annotations

import logging

from app.growth.engagement_feedback import refresh_engagement_feedback
from app.growth.source_yield import refresh_source_yield_scores
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


async def run_growth_feedback_tick(ctx: object) -> dict[str, int | float]:
    settings = ctx.settings  # type: ignore[attr-defined]
    runtime_dir = settings.runtime_state_dir
    result: dict[str, int | float] = {}
    try:
        fb = await refresh_engagement_feedback(runtime_dir)
        result["global_engagement"] = fb.global_engagement
        result["momentum"] = fb.momentum
        result["low_streak"] = fb.low_engagement_streak
    except Exception as exc:
        log_event(logger, "growth.feedback_failed", error=repr(exc)[:200])
    try:
        result["sources_updated"] = await refresh_source_yield_scores()
    except Exception as exc:
        log_event(logger, "growth.source_yield_failed", error=repr(exc)[:200])
    log_event(logger, "growth.feedback_tick_complete", **{k: v for k, v in result.items()})
    return result
