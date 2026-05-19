from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from bot.digest.service import DigestService
from bot.runtime.adaptive_scheduler import AdaptiveScheduler
from bot.storage.digest_repository import DIGEST_HOURLY, DIGEST_MORNING

logger = logging.getLogger(__name__)

_CHECK_INTERVAL_SEC = 60
_MORNING_UTC_HOUR = 8


async def run_digest_scheduler(
    service: DigestService,
    *,
    cluster_scheduler: AdaptiveScheduler | None = None,
) -> None:
    """Background scheduler: morning at 08:00 UTC, hourly every 60 minutes."""
    last_hourly_at: datetime | None = None
    last_morning_date: datetime | None = None

    logger.info("event=digest_scheduler_started")

    while True:
        try:
            now = datetime.now(timezone.utc)

            try:
                from bot.editorial.flow_health.recovery import try_recovery_digest

                await try_recovery_digest(service)
            except Exception:
                pass

            if now.hour == _MORNING_UTC_HOUR and now.minute < 2:
                if last_morning_date is None or last_morning_date.date() != now.date():
                    if cluster_scheduler is None or cluster_scheduler.try_schedule(
                        "digest_morning",
                        qos_class="digest",
                    ).acquired:
                        await service.run_digest(DIGEST_MORNING)
                        last_morning_date = now

            if last_hourly_at is None or (now - last_hourly_at).total_seconds() >= 3600:
                if cluster_scheduler is None or cluster_scheduler.try_schedule(
                    "digest_hourly",
                    qos_class="digest",
                ).acquired:
                    await service.run_digest(DIGEST_HOURLY)
                    last_hourly_at = now
        except asyncio.CancelledError:
            logger.info("event=digest_scheduler_stopped")
            raise
        except Exception:
            logger.exception("event=digest_scheduler_tick_failed")

        await asyncio.sleep(_CHECK_INTERVAL_SEC)
