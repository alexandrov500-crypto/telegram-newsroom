from __future__ import annotations

import asyncio

from tests.conftest import minimal_test_settings
from utils.runtime_health import gather_runtime_health


def test_gather_runtime_health_database_false_after_close() -> None:
    from db.session import close_db, init_db

    s = minimal_test_settings()

    async def body() -> None:
        await init_db(s.database_url, pool_size=s.database_pool_size, max_overflow=s.database_max_overflow)
        await close_db()
        snap = await gather_runtime_health(s)
        assert snap["checks"]["database"]["ok"] is False
        assert snap["ok"] is False

    asyncio.run(body())
