"""aiogram publish retry bounded behavior."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from publisher.retry import async_retry


def test_async_retry_three_attempts() -> None:
    async def body() -> None:
        calls = 0

        async def flaky() -> str:
            nonlocal calls
            calls += 1
            if calls < 3:
                raise TimeoutError("simulated")
            return "ok"

        out = await async_retry(flaky, attempts=3, delay_sec=0, label="chunk")
        assert out == "ok"
        assert calls == 3

    asyncio.run(body())


def test_async_retry_fails_after_attempts() -> None:
    async def body() -> None:
        op = AsyncMock(side_effect=RuntimeError("fail"))

        try:
            await async_retry(op, attempts=2, delay_sec=0, label="chunk")
        except RuntimeError:
            assert op.await_count == 2
        else:
            raise AssertionError("expected failure")

    asyncio.run(body())
