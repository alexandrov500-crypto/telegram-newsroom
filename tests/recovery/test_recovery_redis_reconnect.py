from __future__ import annotations

import asyncio

from tests.conftest import minimal_test_settings


def test_reconnect_redis_when_disabled_returns_false() -> None:
    from utils.redis_client import reconnect_redis

    s = minimal_test_settings(redis_enabled=False)

    async def body() -> None:
        ok = await reconnect_redis(s)
        assert ok is False

    asyncio.run(body())
