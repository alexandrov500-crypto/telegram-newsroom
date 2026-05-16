from __future__ import annotations

import asyncio

import pytest

from worker.job_queue import JobEnvelope, JobKind, JobRetryMeta
from worker.reliable_transport import InMemoryReliableTransport


@pytest.fixture
def rt() -> InMemoryReliableTransport:
    return InMemoryReliableTransport()


def test_memory_recover_stale_requeues(rt: InMemoryReliableTransport) -> None:
    async def body() -> None:
        shutdown = asyncio.Event()
        await rt.enqueue(
            JobEnvelope(
                JobKind.INGEST,
                {"job_type": "INGEST_ARTICLE", "x": 1},
                retry=JobRetryMeta(),
            ),
        )
        lease = await rt.lease_dequeue(JobKind.INGEST, shutdown=shutdown, visibility_sec=0.1, poll_timeout_sec=0.2)
        assert lease is not None
        raw, _env = lease
        await asyncio.sleep(0.2)
        n = await rt.recover_stale(JobKind.INGEST, visibility_sec=0.1)
        assert n == 1
        lease2 = await rt.lease_dequeue(JobKind.INGEST, shutdown=shutdown, visibility_sec=5, poll_timeout_sec=1.0)
        assert lease2 is not None

    asyncio.run(body())


def test_memory_dlq(rt: InMemoryReliableTransport) -> None:
    async def body() -> None:
        await rt.enqueue(JobEnvelope(JobKind.AI, {"job_type": "GENERATE_SUMMARY"}, retry=JobRetryMeta()))
        shutdown = asyncio.Event()
        lease = await rt.lease_dequeue(JobKind.AI, shutdown=shutdown, visibility_sec=60, poll_timeout_sec=1.0)
        assert lease is not None
        raw, env = lease
        did = str(env.payload["delivery_id"])
        await rt.nack_dlq(JobKind.AI, raw, delivery_id=did, reason="test")
        rows = rt.memory_dlq_snapshot(JobKind.AI)
        assert len(rows) == 1
        assert rows[0].get("schema_version") == 1
        assert rows[0].get("delivery_id") == did

    asyncio.run(body())
