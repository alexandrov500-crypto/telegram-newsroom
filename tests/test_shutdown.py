from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app import lifecycle


@pytest.fixture(autouse=True)
def reset_shutdown_gate():
    lifecycle.reset_shutdown_state_for_tests()
    yield
    lifecycle.reset_shutdown_state_for_tests()


def test_graceful_shutdown_idempotent():
    async def body() -> None:
        sched = MagicMock()
        openai = MagicMock()
        openai.close = AsyncMock()
        bot = MagicMock()
        bot.session = MagicMock()
        bot.session.close = AsyncMock()

        first = await lifecycle.graceful_shutdown(scheduler=sched, openai=openai, bot=bot)
        second = await lifecycle.graceful_shutdown(scheduler=sched, openai=openai, bot=bot)

        assert first is True
        assert second is False
        assert sched.shutdown.call_count == 1
        openai.close.assert_awaited()
        bot.session.close.assert_awaited()

    asyncio.run(body())


def test_graceful_shutdown_without_scheduler_closes_db_safe():
    async def body() -> None:
        from db.session import close_db

        await close_db()
        ok = await lifecycle.graceful_shutdown(scheduler=None, openai=None, bot=None)
        assert ok is True

    asyncio.run(body())


def test_repeated_shutdown_after_reset_runs_again():
    async def body() -> None:
        sched = MagicMock()
        await lifecycle.graceful_shutdown(scheduler=sched, openai=None, bot=None)
        assert sched.shutdown.call_count == 1

        lifecycle.reset_shutdown_state_for_tests()
        sched2 = MagicMock()
        await lifecycle.graceful_shutdown(scheduler=sched2, openai=None, bot=None)
        assert sched2.shutdown.call_count == 1

    asyncio.run(body())
