"""Forensic Bot media guards."""

from __future__ import annotations

import asyncio

import pytest

from publisher.telegram_forensic import assert_media_kwargs_fail_closed, install_media_send_forensic_guards


def test_forbidden_kwargs_fail_closed() -> None:
    with pytest.raises(RuntimeError, match="Forbidden media kwargs"):
        assert_media_kwargs_fail_closed(
            {"chat_id": 1, "disable_web_page_preview": True},
            transport_method="send_video",
            caller_module="test",
        )


def test_bot_class_send_video_forensic_rejects_legacy_kwarg() -> None:
    install_media_send_forensic_guards()
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties

    async def _run() -> None:
        bot = Bot(
            token="123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw",
            default=DefaultBotProperties(),
        )
        await bot.send_video(chat_id=-1001, video="file_id_placeholder", disable_web_page_preview=True)

    with pytest.raises(RuntimeError, match="Forbidden media kwargs"):
        asyncio.run(_run())
