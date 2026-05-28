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


def test_publish_photo_no_web_preview_kwarg(fake_settings: Settings, tmp_path) -> None:
    async def body() -> None:
        img = tmp_path / "pic.jpg"
        img.write_bytes(b"z" * 600)
        import json

        extras = json.dumps({"media": {"media_type": "photo", "local_path": str(img)}})
        bot = MagicMock()
        sent = MagicMock()
        sent.message_id = 77
        bot.send_photo = AsyncMock(return_value=sent)

        await publish_draft_to_channel(
            bot,
            fake_settings,
            draft_id=4,
            content="Photo story",
            draft_extras_json=extras,
        )
        bot.send_photo.assert_awaited()
        _, kwargs = bot.send_photo.await_args
        assert "disable_web_page_preview" not in kwargs

    asyncio.run(body())


def test_text_message_keeps_web_preview_flag(fake_settings: Settings) -> None:
    async def body() -> None:
        bot = MagicMock()
        sent = MagicMock()
        sent.message_id = 42
        bot.send_message = AsyncMock(return_value=sent)

        await publish_draft_to_channel(
            bot,
            fake_settings,
            draft_id=8,
            content="plain text post",
        )
        bot.send_message.assert_awaited()
        _, kwargs = bot.send_message.await_args
        assert kwargs.get("disable_web_page_preview") is True

    asyncio.run(body())


def test_publish_draft_with_photo(fake_settings: Settings, tmp_path) -> None:
    async def body() -> None:
        img = tmp_path / "pic.jpg"
        img.write_bytes(b"z" * 600)
        import json

        extras = json.dumps({"media": {"media_type": "photo", "local_path": str(img)}})
        bot = MagicMock()
        sent = MagicMock()
        sent.message_id = 99
        bot.send_photo = AsyncMock(return_value=sent)

        mid = await publish_draft_to_channel(
            bot,
            fake_settings,
            draft_id=3,
            content="Story with illustration",
            draft_extras_json=extras,
        )
        assert mid == 99
        bot.send_photo.assert_awaited()
        _, kwargs = bot.send_photo.await_args
        assert "disable_web_page_preview" not in kwargs
        bot.send_message.assert_not_called()

    asyncio.run(body())


def test_publish_draft_with_video_no_web_preview_kwarg(fake_settings: Settings, tmp_path) -> None:
    async def body() -> None:
        vid = tmp_path / "clip.mp4"
        vid.write_bytes(b"z" * 600)
        import json

        extras = json.dumps({"media": {"media_type": "video", "local_path": str(vid)}})
        bot = MagicMock()
        sent = MagicMock()
        sent.message_id = 88
        bot.send_video = AsyncMock(return_value=sent)

        mid = await publish_draft_to_channel(
            bot,
            fake_settings,
            draft_id=2,
            content="Роспотребнадзор приостановил ввоз воды",
            draft_extras_json=extras,
        )
        assert mid == 88
        bot.send_video.assert_awaited()
        _, kwargs = bot.send_video.await_args
        assert "disable_web_page_preview" not in kwargs

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
