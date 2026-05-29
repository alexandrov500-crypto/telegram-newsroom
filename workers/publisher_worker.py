"""Publisher worker entrypoint (JobKind.PUBLISHER)."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.enums import ParseMode

from worker.job_queue import JobKind

from workers.base import WorkerRole
from workers.bootstrap import init_worker_stack, teardown_worker_stack
from workers.handlers import build_publisher_registry
from workers.runtime import WorkerRuntime

logger = logging.getLogger(__name__)


async def _async_main() -> None:
    from app.config import load_settings

    settings = load_settings()
    await init_worker_stack(settings)
    from app.telegram_bot import create_newsroom_bot

    bot = create_newsroom_bot(settings)
    registry = build_publisher_registry()
    rt = WorkerRuntime(
        settings,
        role=WorkerRole.PUBLISHER,
        job_kind=JobKind.PUBLISHER,
        registry=registry,
        bot=bot,
    )
    rt.install_signals()
    try:
        await rt.run_forever()
    finally:
        try:
            await bot.session.close()
        except Exception:
            logger.exception("publisher_worker.bot_close_failed")
        await teardown_worker_stack()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_async_main())


if __name__ == "__main__":
    main()
