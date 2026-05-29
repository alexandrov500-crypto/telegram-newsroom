from __future__ import annotations

import logging
import os
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
    if (session_string or "").strip():
        session = StringSession(session_string.strip())
        log_event(logger, "telethon.session_backend", backend="string")
    elif session_path:
        session = SQLiteSession(session_path)
        log_event(logger, "telethon.session_backend", backend="sqlite", path=session_path)
    else:
        session = StringSession("")
        log_event(logger, "telethon.session_backend", backend="string", empty=True)

    use_ipv6 = os.getenv("TELETHON_USE_IPV6", "false").strip().lower() in ("1", "true", "yes", "on")
    log_event(logger, "telethon.transport", use_ipv6=use_ipv6)
    return TelegramClient(session, api_id, api_hash, use_ipv6=use_ipv6)


def to_utc_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
