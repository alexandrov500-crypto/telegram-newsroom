from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import FloodWaitError

from bot.config import project_root

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TelethonSettings:
    api_id: int
    api_hash: str
    session_name: str
    source_channels: tuple[str, ...]


def session_path(session_name: str) -> Path:
    safe = session_name.strip() or "newsroom_session"
    return project_root() / safe


def create_telegram_client(settings: TelethonSettings) -> TelegramClient:
    return TelegramClient(
        str(session_path(settings.session_name)),
        settings.api_id,
        settings.api_hash,
    )


async def ensure_connected(client: TelegramClient) -> bool:
    if client.is_connected():
        return True
    try:
        await client.connect()
        if not await client.is_user_authorized():
            logger.error(
                "event=telegram_ingestion_failed reason=session_not_authorized "
                "hint='run telethon login once for this session file'"
            )
            return False
        return True
    except Exception:
        logger.exception("event=telegram_ingestion_failed reason=connect_error")
        return False


async def handle_flood_wait(exc: FloodWaitError) -> None:
    wait_sec = int(exc.seconds)
    logger.warning("event=telegram_flood_wait wait_sec=%d", wait_sec)
    import asyncio

    await asyncio.sleep(wait_sec + 1)
