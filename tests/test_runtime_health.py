from __future__ import annotations

import asyncio

from tests.conftest import minimal_test_settings


def test_gather_runtime_health_sqlite() -> None:
    from db.session import close_db, init_db
    from utils.redis_client import close_redis, init_redis_from_settings
    from utils.runtime_health import gather_runtime_health
    from worker.job_queue import close_job_queue, init_job_queue

    s = minimal_test_settings()

    async def body() -> None:
        await init_db(s.database_url, pool_size=s.database_pool_size, max_overflow=s.database_max_overflow)
        await init_redis_from_settings(s)
        await init_job_queue(s)
        try:
            snap = await gather_runtime_health(s)
            assert snap["checks"]["database"]["ok"] is True
            assert snap["database_backend"] == "sqlite"
        finally:
            await close_job_queue()
            await close_redis()
            await close_db()

    asyncio.run(body())
