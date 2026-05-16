from __future__ import annotations

import asyncio

import pytest

import scheduler.pipeline_lock as pl


def test_lock_released_after_exception():
    async def body() -> None:
        lock = pl.get_pipeline_lock()
        with pytest.raises(ValueError, match="boom"):
            async with lock:
                raise ValueError("boom")
        assert not lock.locked()

    asyncio.run(body())


def test_async_with_lock_acquire_release():
    async def body() -> None:
        lock = pl.get_pipeline_lock()
        assert not lock.locked()
        async with lock:
            assert lock.locked()
        assert not lock.locked()

    asyncio.run(body())


def test_second_waiter_times_out_while_lock_held():
    async def body() -> None:
        lock = pl.get_pipeline_lock()
        started = asyncio.Event()

        async def holder() -> None:
            async with lock:
                started.set()
                await asyncio.sleep(0.2)

        async def waiter() -> None:
            await started.wait()
            await asyncio.wait_for(lock.acquire(), timeout=0.05)

        h = asyncio.create_task(holder())
        w = asyncio.create_task(waiter())
        with pytest.raises(asyncio.TimeoutError):
            await w
        await h

    asyncio.run(body())
