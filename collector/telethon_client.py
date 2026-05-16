from __future__ import annotations

import logging
from datetime import datetime, timezone

from telethon import TelegramClient
from telethon.sessions import SQLiteSession, StringSession

from utils.structured_log import log_event

logger = logging.getLogger(__name__)


def build_telethon_client(
    *,
    api_id: int,
    api_hash: str,
    session_string: str | None = None,
    session_path: str | None = None,
) -> TelegramClient:
    if session_path:
        session = SQLiteSession(session_path)
        log_event(logger, "telethon.session_backend", backend="sqlite", path=session_path)
    else:
        session = StringSession(session_string or "")
        log_event(logger, "telethon.session_backend", backend="string")

    return TelegramClient(session, api_id, api_hash)


def to_utc_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
