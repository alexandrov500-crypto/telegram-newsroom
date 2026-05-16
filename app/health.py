from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from openai import AsyncOpenAI
from sqlalchemy import text

from app.config import Settings
from collector.telethon_client import build_telethon_client
from db.session import get_engine
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


async def run_startup_healthchecks(
    settings: Settings,
    bot: Bot,
    openai: AsyncOpenAI,
    *,
    health_timeout_sec: float = 12.0,
) -> None:
    errors: list[str] = []

    try:
        engine = get_engine()

        async def _db() -> None:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))

        await asyncio.wait_for(_db(), timeout=health_timeout_sec)
        log_event(logger, "healthcheck.database_ok")
    except Exception as exc:
        errors.append(f"database: {exc}")
        logger.exception("Healthcheck: database failed")

    try:
        from utils.redis_client import redis_client_active, redis_ping_ok

        if settings.redis_enabled:
            if redis_client_active():
                pr = await asyncio.wait_for(redis_ping_ok(), timeout=health_timeout_sec)
                if pr is True:
                    log_event(logger, "healthcheck.redis_ok")
                else:
                    log_event(logger, "healthcheck.redis_degraded", recovery="ping_failed_non_fatal")
            else:
                log_event(logger, "healthcheck.redis_skipped", recovery="enabled_but_not_connected")
    except Exception as exc:
        log_event(logger, "healthcheck.redis_check_failed", error=repr(exc), recovery="non_fatal")

    try:
        await asyncio.wait_for(
            openai.models.retrieve(settings.openai_model),
            timeout=health_timeout_sec,
        )
        log_event(logger, "healthcheck.openai_ok", model=settings.openai_model)
    except Exception as exc:
        errors.append(f"openai: {exc}")
        logger.exception("Healthcheck: OpenAI API failed")

    try:
        me = await asyncio.wait_for(bot.get_me(), timeout=health_timeout_sec)
        log_event(logger, "healthcheck.telegram.bot_ok", bot_id=me.id, username=me.username or "")
    except Exception as exc:
        errors.append(f"telegram_bot: {exc}")
        logger.exception("Healthcheck: Telegram bot auth failed")

    client = build_telethon_client(
        api_id=settings.telegram_api_id,
        api_hash=settings.telegram_api_hash,
        session_string=settings.telethon_session_string,
        session_path=settings.telethon_session_path,
    )
    try:

        async def _telethon() -> None:
            await client.connect()
            if not await client.is_user_authorized():
                raise RuntimeError("session not authorized")

        await asyncio.wait_for(_telethon(), timeout=health_timeout_sec)
        log_event(logger, "healthcheck.telegram.telethon_ok")
    except Exception as exc:
        errors.append(f"telethon: {exc}")
        logger.exception("Healthcheck: Telethon auth failed")
    finally:
        if client.is_connected():
            await client.disconnect()

    if errors:
        msg = "; ".join(errors)
        raise RuntimeError(f"Startup healthchecks failed: {msg}")

    log_event(logger, "healthcheck.all_ok")
