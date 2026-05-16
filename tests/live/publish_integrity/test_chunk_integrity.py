"""Chunk splitting and partial publish semantics (no Telegram API)."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from tests.conftest import minimal_test_settings
from utils.telegram_chunks import split_telegram_text


def test_split_respects_html_chunks() -> None:
    html = "<b>hello</b> " + "x" * 5000
    chunks = split_telegram_text(html, respect_html=True)
    assert len(chunks) >= 2
    for c in chunks:
        assert len(c) <= 4096


def test_partial_chunk_failure_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    async def body() -> None:
        from publisher import telegram_publisher as tp

        monkeypatch.setattr(tp, "split_telegram_text", lambda *a, **k: ["c1", "c2", "c3"])
        s = minimal_test_settings(
            publish_channel_min_interval_sec=0.0,
            publish_burst_window_sec=60.0,
            publish_burst_max_messages=10,
            telegram_inter_chunk_delay_sec=0.0,
        )
        bot = AsyncMock()
        call_n = 0

        async def send_message(**kwargs):
            nonlocal call_n
            call_n += 1
            if call_n >= 2:
                raise RuntimeError("simulated partial publish")
            m = AsyncMock()
            m.message_id = call_n
            return m

        bot.send_message = send_message
        with pytest.raises(RuntimeError, match="partial publish"):
            await tp.publish_draft_to_channel(
                bot,
                s,
                draft_id=1,
                content="ignored",
                sources="[]",
            )

    import asyncio

    asyncio.run(body())


def test_publish_lock_redis_contention_yields_false(monkeypatch: pytest.MonkeyPatch) -> None:
    async def body() -> None:
        from publisher.publish_lock import publish_draft_lock
        from tests.chaos.framework import make_fake_redis

        holder: dict[str, object] = {}

        async def get_redis() -> object:
            return holder.get("client")

        monkeypatch.setattr("utils.redis_client.get_redis", get_redis)
        fake = make_fake_redis(set_ok=True)
        holder["client"] = fake
        s = minimal_test_settings(redis_enabled=True, publish_lock_strict=False)
        async with publish_draft_lock(s, 7002) as ok1:
            assert ok1 is True
        fake.set = AsyncMock(return_value=False)
        async with publish_draft_lock(s, 7002) as ok2:
            assert ok2 is False

    import asyncio

    asyncio.run(body())
