"""Opt-in live Telethon connectivity (requires credentials)."""

from __future__ import annotations

import asyncio

import pytest

from collector.retry import ensure_connected
from collector.telethon_client import build_telethon_client
from tests.live.conftest import live_telegram_enabled


@pytest.mark.live_telegram
def test_live_connect_and_disconnect(live_telegram_guard) -> None:
    if not live_telegram_enabled():
        pytest.skip("TELEGRAM_LIVE_VALIDATE not set")

    from app.config import load_settings

    s = load_settings()

    async def body() -> None:
        client = build_telethon_client(
            api_id=s.telegram_api_id,
            api_hash=s.telegram_api_hash,
            session_string=s.telethon_session_string,
            session_path=s.telethon_session_path,
        )
        await ensure_connected(client)
        assert client.is_connected()
        await client.disconnect()

    asyncio.run(body())
