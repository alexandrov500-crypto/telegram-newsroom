from __future__ import annotations

import asyncio

from tests.conftest import minimal_test_settings
from worker.reliable_transport import close_reliable_transport, get_reliable_transport, init_reliable_transport


def test_sqlite_settings_initializes_memory_transport() -> None:
    """Development stack: SQLite URL + in-memory reliable transport (no Redis)."""

    async def body() -> None:
        s = minimal_test_settings(redis_enabled=False)
        await init_reliable_transport(s)
        try:
            t = get_reliable_transport()
            from worker.job_queue import JobEnvelope, JobKind, JobRetryMeta

            await t.enqueue(JobEnvelope(JobKind.AI, {"job_type": "GENERATE_SUMMARY"}, retry=JobRetryMeta()))
            assert await t.depth_pending(JobKind.AI) == 1
        finally:
            await close_reliable_transport()

    asyncio.run(body())
