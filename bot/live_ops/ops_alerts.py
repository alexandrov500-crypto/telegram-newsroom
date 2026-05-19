from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


async def notify_ops_channel(text: str, *, force: bool = True) -> bool:
    """Route operational alerts to internal ops channel."""
    try:
        from bot.operator_console.context import get_operator_console

        console = get_operator_console()
        if console is not None:
            await console.send_raw(text, category="alert", force=force)
            return True
    except Exception:
        logger.exception("event=ops_channel_console_failed")

    ops_chat = os.getenv("LIVE_OPS_CHANNEL_ID") or os.getenv("TELEGRAM_OPERATOR_CHAT_ID")
    if not ops_chat:
        logger.warning("event=ops_channel_unconfigured text=%s", text[:80])
        return False
    try:
        from aiogram import Bot
        from bot.settings import get_settings

        settings = get_settings()
        token = settings.bot_token or settings.telegram_bot_token
        if not token:
            return False
        bot = Bot(token=token)
        await bot.send_message(int(ops_chat), text, parse_mode="HTML")
        await bot.session.close()
        return True
    except Exception:
        logger.exception("event=ops_channel_direct_send_failed")
        return False
