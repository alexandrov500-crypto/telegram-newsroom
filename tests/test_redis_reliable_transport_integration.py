from __future__ import annotations

import asyncio
import os
import uuid

import pytest

from tests.conftest import minimal_test_settings
from tests.helpers.redis_proxy import BrpoplpushFailProxy
from worker.job_queue import JobEnvelope, JobKind, JobRetryMeta
from worker.reliable_transport import RedisReliableTransport

pytestmark = pytest.mark.skipif(
    not os.getenv("NEWSROOM_TEST_REDIS_URL"),
    reason="NEWSROOM_TEST_REDIS_URL not set (optional real Redis integration)",
)


async def _cleanup_prefix(r, prefix: str) -> None:
    pattern = f"{prefix}*"
    async for key in r.scan_iter(match=pattern):
        await r.delete(key)


def test_brpoplpush_ack_roundtrip() -> None:
    from redis.asyncio import Redis

    url = os.environ["NEWSROOM_TEST_REDIS_URL"]

    async def body() -> None:
        r = Redis.from_url(url, decode_responses=True)
        prefix = f"nr_test_{uuid.uuid4().hex[:12]}"
        s = minimal_test_settings(redis_enabled=True, redis_url=url, job_queue_prefix=prefix)
        t = RedisReliableTransport(r, prefix=prefix, settings=s)
        try:
            await t.enqueue(JobEnvelope(JobKind.AI, {"job_type": "X", "n": 1}, retry=JobRetryMeta()))
            shutdown = asyncio.Event()
            lease = await t.lease_dequeue(JobKind.AI, shutdown=shutdown, visibility_sec=120, poll_timeout_sec=2.0)
            assert lease is not None
            raw, env = lease
            did = str(env.payload["delivery_id"])
            assert await t.depth_processing(JobKind.AI) >= 1
            await t.ack(JobKind.AI, raw, delivery_id=did)
            assert await t.depth_pending(JobKind.AI) == 0
            assert await t.depth_processing(JobKind.AI) == 0
        finally:
            await _cleanup_prefix(r, prefix)
            await r.aclose()

    asyncio.run(body())


def test_recover_stale_after_inflight_deleted() -> None:
    from redis.asyncio import Redis

    url = os.environ["NEWSROOM_TEST_REDIS_URL"]

    async def body() -> None:
        r = Redis.from_url(url, decode_responses=True)
        prefix = f"nr_test_{uuid.uuid4().hex[:12]}"
        s = minimal_test_settings(redis_enabled=True, redis_url=url, job_queue_prefix=prefix)
        t = RedisReliableTransport(r, prefix=prefix, settings=s)
        try:
            await t.enqueue(JobEnvelope(JobKind.INGEST, {"job_type": "INGEST_ARTICLE"}, retry=JobRetryMeta()))
            shutdown = asyncio.Event()
            lease = await t.lease_dequeue(JobKind.INGEST, shutdown=shutdown, visibility_sec=30, poll_timeout_sec=2.0)
            assert lease is not None
            raw, env = lease
            did = str(env.payload["delivery_id"])
            await r.delete(f"{prefix}:inflight:{did}")
            moved = await t.recover_stale(JobKind.INGEST, visibility_sec=30)
            assert moved == 1
            lease2 = await t.lease_dequeue(JobKind.INGEST, shutdown=shutdown, visibility_sec=120, poll_timeout_sec=2.0)
            assert lease2 is not None
            raw2, _ = lease2
            assert raw2 == raw
            await t.ack(JobKind.INGEST, raw2, delivery_id=did)
        finally:
            await _cleanup_prefix(r, prefix)
            await r.aclose()

    asyncio.run(body())


def test_dlq_list_second_transport_same_redis() -> None:
    from redis.asyncio import Redis

    url = os.environ["NEWSROOM_TEST_REDIS_URL"]

    async def body() -> None:
        r = Redis.from_url(url, decode_responses=True)
        prefix = f"nr_test_{uuid.uuid4().hex[:12]}"
        s = minimal_test_settings(redis_enabled=True, redis_url=url, job_queue_prefix=prefix)
        t = RedisReliableTransport(r, prefix=prefix, settings=s)
        try:
            await t.enqueue(JobEnvelope(JobKind.PUBLISHER, {"job_type": "PUBLISH_DRAFT"}, retry=JobRetryMeta()))
            shutdown = asyncio.Event()
            lease = await t.lease_dequeue(JobKind.PUBLISHER, shutdown=shutdown, visibility_sec=120, poll_timeout_sec=2.0)
            assert lease is not None
            raw, env = lease
            did = str(env.payload["delivery_id"])
            await t.nack_dlq(
                JobKind.PUBLISHER,
                raw,
                delivery_id=did,
                reason="unit",
                dlq_meta={"terminal": "permanent"},
            )
            t2 = RedisReliableTransport(r, prefix=prefix, settings=s)
            rows2 = await t2.list_dlq(JobKind.PUBLISHER, limit=5)
            assert len(rows2) == 1
            assert rows2[0].get("delivery_id") == did
        finally:
            await _cleanup_prefix(r, prefix)
            await r.aclose()

    asyncio.run(body())


def test_brpoplpush_recovers_after_transient_failures() -> None:
    from redis.asyncio import Redis

    url = os.environ["NEWSROOM_TEST_REDIS_URL"]

    async def body() -> None:
        r = Redis.from_url(url, decode_responses=True)
        prefix = f"nr_test_{uuid.uuid4().hex[:12]}"
        s = minimal_test_settings(redis_enabled=True, redis_url=url, job_queue_prefix=prefix)
        inner = BrpoplpushFailProxy(r, fail_brpoplpush=2)
        t = RedisReliableTransport(inner, prefix=prefix, settings=s)
        try:
            await t.enqueue(JobEnvelope(JobKind.AI, {"job_type": "X"}, retry=JobRetryMeta()))
            shutdown = asyncio.Event()
            lease = await t.lease_dequeue(JobKind.AI, shutdown=shutdown, visibility_sec=120, poll_timeout_sec=2.0)
            assert lease is not None
            raw, env = lease
            await t.ack(JobKind.AI, raw, delivery_id=str(env.payload["delivery_id"]))
        finally:
            await _cleanup_prefix(r, prefix)
            await r.aclose()

    asyncio.run(body())
