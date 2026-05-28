"""Aiogram Bot factory with production HTTP timeouts (aiogram 3.7+)."""
from __future__ import annotations

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode

from app.config import Settings


def create_newsroom_bot(settings: Settings) -> Bot:
    """Bot with AiohttpSession timeout; close via ``await bot.session.close()`` on shutdown."""
    from publisher.telegram_forensic import install_media_send_forensic_guards

    install_media_send_forensic_guards()
    session = AiohttpSession(timeout=settings.telegram_http_timeout_sec)
    return Bot(
        settings.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
