from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.operator_console.formatting import split_message
from bot.operator_console.rate_limit import RateLimiter
from bot.settings import BotSettings


def test_split_message_long() -> None:
    text = "line\n" * 500
    parts = split_message(text, max_len=100)
    assert len(parts) > 1
    assert all(len(p) <= 100 for p in parts)


def test_rate_limiter_burst() -> None:
    lim = RateLimiter(default_cooldown_sec=0.0)
    for _ in range(5):
        assert lim.allow("test", cooldown_sec=0.0, max_burst=5)
    assert not lim.allow("test", cooldown_sec=0.0, max_burst=5)


def test_notify_ingest_respects_enabled() -> None:
    import asyncio

    from bot.operator_console.console import OperatorTelegramConsole

    async def _run() -> None:
        bot = AsyncMock()
        settings = BotSettings(
            TELEGRAM_BOT_TOKEN="x" * 20,
            TELEGRAM_LIVE_INGEST_ENABLED=False,
            TELEGRAM_OPERATOR_CHAT_ID=-100123,
        )
        console = OperatorTelegramConsole(bot, settings)
        await console.notify_ingest(
            source="reuters",
            language="en",
            headline="Test headline",
            outcome="enqueued",
            confidence=0.8,
            cluster_id=1,
            news_id=42,
            priority=0.9,
        )
        bot.send_message.assert_not_called()

    asyncio.run(_run())
