"""W5 maintenance — profitability refresh, sponsor cap reset, audience value map."""

from __future__ import annotations

import logging

from app.monetization.audience_value import save_cohort_monetization_map
from app.monetization.financial_feedback import refresh_topic_profitability
from app.monetization.sponsor_injection import reset_daily_sponsor_caps
from utils.structured_log import log_event

logger = logging.getLogger(__name__)

COHORTS = ("macro", "crypto", "geopolitics", "finance", "energy", "corporate")


async def run_monetization_maintenance_tick(ctx: object) -> dict[str, object]:
    settings = ctx.settings  # type: ignore[attr-defined]
    runtime_dir = settings.runtime_state_dir
    result: dict[str, object] = {}
    try:
        result["profitability"] = await refresh_topic_profitability()
    except Exception as exc:
        log_event(logger, "monetization.profitability_failed", error=repr(exc)[:200])
    try:
        result["sponsor_reset"] = await reset_daily_sponsor_caps()
    except Exception as exc:
        log_event(logger, "monetization.sponsor_reset_failed", error=repr(exc)[:200])
    try:
        result["audience_value"] = save_cohort_monetization_map(runtime_dir, COHORTS)
    except Exception as exc:
        log_event(logger, "monetization.audience_value_failed", error=repr(exc)[:200])
    log_event(logger, "monetization.maintenance_complete", keys=list(result.keys()))
    return result
