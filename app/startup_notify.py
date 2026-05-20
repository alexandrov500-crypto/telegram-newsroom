"""Backward-compatible entrypoint for process startup Telegram notification."""
from __future__ import annotations

from aiogram import Bot

from app.config import Settings
from app.runtime_notifications import maybe_send_process_startup_notification


async def send_startup_banner(bot: Bot, settings: Settings) -> None:
    """Send startup banner once per process boot (not on polling reconnect)."""
    await maybe_send_process_startup_notification(bot, settings, trigger="process_boot")
