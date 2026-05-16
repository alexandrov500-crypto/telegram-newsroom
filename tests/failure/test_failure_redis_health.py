from __future__ import annotations

import asyncio

from tests.conftest import minimal_test_settings
from tests.helpers.failure_injection import redis_get_returns_none, redis_ping_raises
from utils.runtime_health import gather_runtime_health


def test_runtime_health_redis_degraded_when_get_returns_none() -> None:
    from db.session import close_db, init_db

    s = minimal_test_settings(redis_enabled=True)

    async def body() -> None:
        await init_db(s.database_url, pool_size=s.database_pool_size, max_overflow=s.database_max_overflow)
        try:
            with redis_get_returns_none():
                snap = await gather_runtime_health(s)
                assert snap["checks"]["redis"]["mode"] == "degraded_connect_failed"
        finally:
            await close_db()

    asyncio.run(body())


def test_runtime_health_redis_ping_false_marks_unhealthy() -> None:
    from db.session import close_db, init_db

    s = minimal_test_settings(redis_enabled=True)

    async def body() -> None:
        await init_db(s.database_url, pool_size=s.database_pool_size, max_overflow=s.database_max_overflow)
        try:
            with redis_ping_raises():
                snap = await gather_runtime_health(s)
                assert snap["checks"]["redis"]["ok"] is False
                assert snap["ok"] is False
        finally:
            await close_db()

    asyncio.run(body())
