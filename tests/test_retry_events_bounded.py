from __future__ import annotations

import asyncio

import workers.state as ws


def test_retry_event_ring_bounded_after_many_retries() -> None:
    async def body() -> None:
        ws.reset_worker_runtime_state_for_tests()
        for _ in range(1000):
            await ws.on_retry()
        assert ws._retry_events.maxlen == 512
        assert len(ws._retry_events) == 512

    asyncio.run(body())
