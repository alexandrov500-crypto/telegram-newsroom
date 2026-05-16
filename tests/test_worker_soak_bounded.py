from __future__ import annotations

import asyncio

from worker.job_queue import JobEnvelope, JobKind, JobRetryMeta
from worker.reliable_transport import InMemoryReliableTransport


def test_memory_soak_many_jobs_depth_returns_to_zero() -> None:
    async def body() -> None:
        rt = InMemoryReliableTransport()
        shutdown = asyncio.Event()
        n_jobs = 800
        for i in range(n_jobs):
            await rt.enqueue(
                JobEnvelope(
                    JobKind.INGEST,
                    {"job_type": "INGEST_ARTICLE", "i": i},
                    retry=JobRetryMeta(attempt=0 if i % 3 else 1, max_attempts=5, backoff_sec=0.01),
                ),
            )
        assert await rt.depth_pending(JobKind.INGEST) == n_jobs
        processed = 0
        while processed < n_jobs:
            lease = await rt.lease_dequeue(
                JobKind.INGEST,
                shutdown=shutdown,
                visibility_sec=120,
                poll_timeout_sec=0.15,
            )
            if lease is None:
                continue
            raw, env = lease
            await rt.ack(JobKind.INGEST, raw, delivery_id=str(env.payload["delivery_id"]))
            processed += 1
        assert await rt.depth_pending(JobKind.INGEST) == 0
        assert await rt.depth_processing(JobKind.INGEST) == 0

    asyncio.run(body())


def test_dlq_replay_roundtrip() -> None:
    async def body() -> None:
        rt = InMemoryReliableTransport()
        shutdown = asyncio.Event()
        await rt.enqueue(JobEnvelope(JobKind.AI, {"job_type": "GENERATE_SUMMARY"}, retry=JobRetryMeta()))
        lease = await rt.lease_dequeue(JobKind.AI, shutdown=shutdown, visibility_sec=60, poll_timeout_sec=1.0)
        assert lease is not None
        raw, env = lease
        did = str(env.payload["delivery_id"])
        await rt.nack_dlq(
            JobKind.AI,
            raw,
            delivery_id=did,
            reason="unit",
            dlq_meta={"terminal": "permanent"},
        )
        ok = await rt.replay_dlq_index(JobKind.AI, index=0)
        assert ok is True
        assert len(rt.memory_dlq_snapshot(JobKind.AI)) == 0
        lease2 = await rt.lease_dequeue(JobKind.AI, shutdown=shutdown, visibility_sec=60, poll_timeout_sec=1.0)
        assert lease2 is not None

    asyncio.run(body())
