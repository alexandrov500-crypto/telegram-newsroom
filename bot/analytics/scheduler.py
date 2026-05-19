from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiogram import Bot

from bot.analytics.collector import collect_post_analytics
from bot.storage.analytics_repository import AnalyticsRepository

logger = logging.getLogger(__name__)

DEFAULT_INTERVAL_SEC = 900


async def run_analytics_scheduler(
    repo: AnalyticsRepository,
    bot: Bot,
    *,
    channel_id: int | None,
    telethon_settings: Any | None = None,
    interval_sec: int = DEFAULT_INTERVAL_SEC,
) -> None:
    """Periodically collect Telegram post analytics. Never raises."""
    logger.info("event=analytics_collected action=scheduler_started interval_sec=%d", interval_sec)
    while True:
        try:
            await collect_post_analytics(
                repo,
                bot,
                channel_id=channel_id,
                telethon_settings=telethon_settings,
            )
        except asyncio.CancelledError:
            logger.info("event=analytics_collected action=scheduler_stopped")
            raise
        except Exception:
            logger.exception("event=analytics_collected action=scheduler_cycle_failed")
        await asyncio.sleep(interval_sec)
