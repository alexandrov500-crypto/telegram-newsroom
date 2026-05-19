from __future__ import annotations

import asyncio

from bot.observability.logging_setup import get_logger
from bot.storage.observability_repository import ObservabilityRepository

logger = get_logger(__name__)

_DAILY_INTERVAL_SEC = 3600


async def run_openai_daily_aggregation_loop(
    repo: ObservabilityRepository,
    *,
    interval_sec: int = _DAILY_INTERVAL_SEC,
) -> None:
    while True:
        try:
            repo.aggregate_daily()
            logger.info("event=openai_daily_aggregate_completed")
        except Exception:
            logger.exception("event=openai_daily_aggregate_failed")
        await asyncio.sleep(interval_sec)
