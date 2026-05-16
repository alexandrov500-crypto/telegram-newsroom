from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.enums import ParseMode

from app.config import Settings
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


async def send_startup_banner(bot: Bot, settings: Settings) -> None:
    if not settings.startup_telegram_notify:
        return
    lines = [
        "<b>Newsroom started</b>",
        f"DRY_RUN=<code>{settings.dry_run}</code>",
        f"SOAK_TEST=<code>{settings.soak_test}</code>",
        f"source_channels={len(settings.source_channels)}",
        f"pipeline_interval_min={settings.pipeline_interval_minutes}",
    ]
    try:
        await bot.send_message(
            settings.admin_user_id,
            "\n".join(lines),
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        log_event(logger, "startup.telegram_banner_sent", admin_user_id=settings.admin_user_id)
    except Exception as exc:
        log_event(logger, "startup.telegram_banner_failed", error=repr(exc))
