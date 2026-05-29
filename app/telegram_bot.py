"""Aiogram Bot factory with production HTTP timeouts (aiogram 3.7+)."""
from __future__ import annotations

import os

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode

from app.config import Settings


def create_newsroom_bot(settings: Settings) -> Bot:
    """Bot with AiohttpSession timeout; close via ``await bot.session.close()`` on shutdown.

    When ``TELEGRAM_BOT_PROXY`` is set (e.g. ``http://xray:1081``), the Bot API HTTP
    client is routed through it. Required where this host's direct path to
    ``api.telegram.org`` is blocked/throttled and we tunnel via the same proxy as
    the collector. aiohttp natively supports http(s) proxies (CONNECT tunneling).
    """
    from publisher.telegram_forensic import install_media_send_forensic_guards

    install_media_send_forensic_guards()
    proxy = os.getenv("TELEGRAM_BOT_PROXY", "").strip() or None
    session = AiohttpSession(proxy=proxy, timeout=settings.telegram_http_timeout_sec)
    return Bot(
        settings.bot_token,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
