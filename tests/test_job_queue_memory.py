from __future__ import annotations

import asyncio

import pytest

from worker.job_queue import InMemoryJobQueue, JobEnvelope, JobKind, JobRetryMeta


@pytest.fixture
def mem_queue() -> InMemoryJobQueue:
    return InMemoryJobQueue()


def test_job_envelope_json_roundtrip() -> None:
    j = JobEnvelope(JobKind.INGEST, {"batch": 1}, retry=JobRetryMeta(attempt=2, max_attempts=5, backoff_sec=1.5))
    j2 = JobEnvelope.from_json(j.to_json())
    assert j2.kind == JobKind.INGEST
    assert j2.payload == {"batch": 1}
    assert j2.retry.attempt == 2


def test_in_memory_enqueue_dequeue(mem_queue: InMemoryJobQueue) -> None:
    async def body() -> None:
        await mem_queue.enqueue(JobEnvelope(JobKind.PUBLISHER, {"draft_id": 7}))
        got = await mem_queue.dequeue(JobKind.PUBLISHER, timeout_sec=2.0)
        assert got is not None
        assert got.payload["draft_id"] == 7
        empty = await mem_queue.dequeue(JobKind.PUBLISHER, timeout_sec=0.05)
        assert empty is None

    asyncio.run(body())


def test_in_memory_depth(mem_queue: InMemoryJobQueue) -> None:
    async def body() -> None:
        assert await mem_queue.depth(JobKind.AI) == 0
        await mem_queue.enqueue(JobEnvelope(JobKind.AI, {}))
        assert await mem_queue.depth(JobKind.AI) == 1

    asyncio.run(body())
