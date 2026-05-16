from __future__ import annotations

import asyncio

from worker.job_queue import JobEnvelope, JobKind, JobRetryMeta
from worker.reliable_transport import InMemoryReliableTransport


def test_stuck_lease_recovers_via_recover_stale() -> None:
    async def body() -> None:
        rt = InMemoryReliableTransport()
        shutdown = asyncio.Event()
        await rt.enqueue(
            JobEnvelope(
                JobKind.AI,
                {"job_type": "SOAK", "delivery_id": "vis-1"},
                retry=JobRetryMeta(),
            ),
        )
        lease = await rt.lease_dequeue(JobKind.AI, shutdown=shutdown, visibility_sec=1, poll_timeout_sec=0.2)
        assert lease is not None
        raw, _env = lease
        assert await rt.depth_pending(JobKind.AI) == 0
        assert await rt.depth_processing(JobKind.AI) == 1
        await asyncio.sleep(1.15)
        moved = await rt.recover_stale(JobKind.AI, visibility_sec=1)
        assert moved >= 1
        assert await rt.depth_processing(JobKind.AI) == 0
        assert await rt.depth_pending(JobKind.AI) >= 1
        lease2 = await rt.lease_dequeue(JobKind.AI, shutdown=shutdown, visibility_sec=60, poll_timeout_sec=0.5)
        assert lease2 is not None
        _raw2, env2 = lease2
        assert env2.payload.get("delivery_id") == "vis-1"

    asyncio.run(body())
