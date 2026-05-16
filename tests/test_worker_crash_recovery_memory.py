from __future__ import annotations

import asyncio

from worker.job_queue import JobEnvelope, JobKind, JobRetryMeta
from worker.reliable_transport import InMemoryReliableTransport


def test_memory_visibility_recovery_preserves_delivery_id() -> None:
    async def body() -> None:
        rt = InMemoryReliableTransport()
        shutdown = asyncio.Event()
        await rt.enqueue(
            JobEnvelope(
                JobKind.INGEST,
                {"job_type": "INGEST_ARTICLE", "x": 1},
                retry=JobRetryMeta(),
            ),
        )
        lease = await rt.lease_dequeue(JobKind.INGEST, shutdown=shutdown, visibility_sec=0.08, poll_timeout_sec=0.2)
        assert lease is not None
        _raw, env = lease
        did = str(env.payload["delivery_id"])
        await asyncio.sleep(0.15)
        n = await rt.recover_stale(JobKind.INGEST, visibility_sec=0.08)
        assert n == 1
        lease2 = await rt.lease_dequeue(JobKind.INGEST, shutdown=shutdown, visibility_sec=60, poll_timeout_sec=1.0)
        assert lease2 is not None
        _raw2, env2 = lease2
        assert str(env2.payload["delivery_id"]) == did

    asyncio.run(body())


def test_memory_at_least_once_after_recovery() -> None:
    """After stale recovery, same raw payload is available again (duplicate delivery possible)."""

    async def body() -> None:
        rt = InMemoryReliableTransport()
        shutdown = asyncio.Event()
        await rt.enqueue(
            JobEnvelope(JobKind.AI, {"job_type": "GENERATE_SUMMARY", "n": 1}, retry=JobRetryMeta()),
        )
        lease = await rt.lease_dequeue(JobKind.AI, shutdown=shutdown, visibility_sec=0.05, poll_timeout_sec=0.2)
        assert lease is not None
        raw1, _ = lease
        await asyncio.sleep(0.12)
        await rt.recover_stale(JobKind.AI, visibility_sec=0.05)
        lease2 = await rt.lease_dequeue(JobKind.AI, shutdown=shutdown, visibility_sec=60, poll_timeout_sec=1.0)
        assert lease2 is not None
        raw2, _ = lease2
        assert raw1 == raw2

    asyncio.run(body())
