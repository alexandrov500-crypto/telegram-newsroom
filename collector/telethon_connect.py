"""Resilient Telethon connect/disconnect — timeouts and structured degradation."""

from __future__ import annotations

import asyncio
import logging
import os

from telethon import TelegramClient

from utils.metrics import inc
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


def _connect_timeout_sec() -> float:
    raw = os.getenv("TELETHON_CONNECT_TIMEOUT_SEC", "25").strip()
    try:
        return max(5.0, min(float(raw), 120.0))
    except ValueError:
        return 25.0


async def connect_telethon_resilient(
    client: TelegramClient,
    *,
    label: str = "collector",
) -> bool:
    """
    Connect with wall-clock timeout. Returns False on timeout/transient failure
    (caller may skip collect gracefully).
    """
    timeout = _connect_timeout_sec()
    if client.is_connected():
        return True
    inc("telethon_reconnects")
    log_event(
        logger,
        "telethon.connect.start",
        label=label,
        timeout_sec=timeout,
    )
    try:
        await asyncio.wait_for(client.connect(), timeout=timeout)
    except asyncio.TimeoutError:
        log_event(
            logger,
            "telethon.connect.timeout",
            label=label,
            timeout_sec=timeout,
            dc_hint="check VPN/firewall/DC reachability",
        )
        try:
            await client.disconnect()
        except Exception:
            pass
        return False
    except (OSError, TimeoutError, ConnectionError) as exc:
        log_event(
            logger,
            "telethon.connect.network_error",
            label=label,
            error=repr(exc)[:200],
        )
        try:
            await client.disconnect()
        except Exception:
            pass
        return False
    except Exception as exc:
        log_event(logger, "telethon.connect.failed", label=label, error=repr(exc)[:200])
        raise
    log_event(logger, "telethon.connect.ok", label=label)
    return True


async def disconnect_telethon_safe(client: TelegramClient, *, label: str = "collector") -> None:
    if not client.is_connected():
        return
    try:
        await asyncio.wait_for(client.disconnect(), timeout=15.0)
        log_event(logger, "telethon.disconnect.ok", label=label)
    except Exception as exc:
        log_event(logger, "telethon.disconnect.warn", label=label, error=repr(exc)[:120])
