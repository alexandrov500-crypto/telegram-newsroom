from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.config import Settings
from publisher.telegram_publisher import publish_draft, publish_draft_to_channel
from tests.conftest import minimal_test_settings


@pytest.fixture
def fake_settings() -> Settings:
    return minimal_test_settings(dry_run=False)


def test_publish_draft_to_channel_chunks(fake_settings: Settings) -> None:
    async def body() -> None:
        bot = MagicMock()
        sent = MagicMock()
        sent.message_id = 42
        bot.send_message = AsyncMock(return_value=sent)

        mid = await publish_draft_to_channel(
            bot,
            fake_settings,
            draft_id=7,
            content="short",
        )
        assert mid == 42
        bot.send_message.assert_awaited()

    asyncio.run(body())


def test_publish_draft_alias_matches(fake_settings: Settings) -> None:
    async def body() -> None:
        bot = MagicMock()
        sent = MagicMock()
        sent.message_id = 1
        bot.send_message = AsyncMock(return_value=sent)
        a = await publish_draft_to_channel(bot, fake_settings, draft_id=1, content="x")
        b = await publish_draft(bot, fake_settings, draft_id=1, content="x")
        assert a == b == 1

    asyncio.run(body())
