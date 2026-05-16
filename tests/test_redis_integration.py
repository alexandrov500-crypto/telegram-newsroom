from __future__ import annotations

import asyncio
import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("NEWSROOM_TEST_REDIS_URL"),
    reason="NEWSROOM_TEST_REDIS_URL not set (optional integration)",
)


def test_redis_connect_ping_reconnect() -> None:
    from redis.asyncio import Redis

    url = os.environ["NEWSROOM_TEST_REDIS_URL"]

    async def body() -> None:
        r = Redis.from_url(url, decode_responses=True)
        assert await r.ping() is True
        await r.aclose()
        r2 = Redis.from_url(url, decode_responses=True)
        assert await r2.ping() is True
        await r2.aclose()

    asyncio.run(body())


def test_redis_job_queue_roundtrip() -> None:
    from redis.asyncio import Redis

    from worker.job_queue import JobEnvelope, JobKind, RedisJobQueue

    url = os.environ["NEWSROOM_TEST_REDIS_URL"]

    async def body() -> None:
        r = Redis.from_url(url, decode_responses=True)
        prefix = "newsroom_pytest_tmp"
        q = RedisJobQueue(r, prefix=prefix)
        key = f"{prefix}:jobq:{JobKind.AI.value}"
        await r.delete(key)
        await q.enqueue(JobEnvelope(JobKind.AI, {"n": 1}))
        got = await q.dequeue(JobKind.AI, timeout_sec=3.0)
        assert got is not None
        assert got.payload["n"] == 1
        await r.aclose()

    asyncio.run(body())
