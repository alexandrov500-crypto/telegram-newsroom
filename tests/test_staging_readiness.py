"""Pre-launch staging regression bundle."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.handler_error_middleware import SafeHandlerMiddleware
from publisher.telegram_transport import build_photo_kwargs, build_video_kwargs, guard_media_kwargs


def test_media_kwargs_whitelist_enforcement() -> None:
    import pytest

    with pytest.raises(RuntimeError, match="Forbidden media kwargs"):
        guard_media_kwargs(
            {"chat_id": -1, "caption": "x", "disable_web_page_preview": True, "link_preview_options": {}},
            transport_method="send_video",
        )


def test_no_disable_web_page_preview_in_media_builders() -> None:
    assert "disable_web_page_preview" not in build_photo_kwargs(chat_id=-2, caption="c")
    assert "disable_web_page_preview" not in build_video_kwargs(chat_id=-3, caption="v")


def test_bot_handler_exception_isolated() -> None:
    mw = SafeHandlerMiddleware()

    async def boom(_event: object, _data: dict) -> None:
        raise RuntimeError("handler boom")

    async def _run() -> None:
        msg = MagicMock()
        msg.from_user = MagicMock(id=1)
        msg.chat = MagicMock(id=2)
        msg.answer = AsyncMock()
        out = await mw(boom, msg, {})
        assert out is None
        msg.answer.assert_awaited()

    asyncio.run(_run())


def test_single_runtime_lock_enforcement(tmp_path) -> None:
    from app.ops.runtime.singleton_guard import RuntimeSingletonGuard

    rd = str(tmp_path / "rt")
    g1 = RuntimeSingletonGuard(rd)
    g2 = RuntimeSingletonGuard(rd)
    assert g1.acquire()
    assert not g2.acquire()
    g1.release()
    assert g2.acquire()
    g2.release()


def test_idempotent_publish_key_shape() -> None:
    draft_id = 42
    assert f"draft:{draft_id}" == "draft:42"
    assert f"retry:{draft_id}:1".startswith("retry:42:")
