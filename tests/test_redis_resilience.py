from __future__ import annotations

import asyncio

from tests.conftest import minimal_test_settings
from utils.redis_resilience import monotonic_backoff_sleep_sec, redis_call_with_retry, redis_transient_error


def test_redis_transient_classifier() -> None:
    assert redis_transient_error(ConnectionResetError()) is True
    assert redis_transient_error(ValueError("bad")) is False


def test_redis_call_with_retry_recovers() -> None:
    async def body() -> None:
        s = minimal_test_settings()
        calls = {"n": 0}

        async def flaky() -> str:
            calls["n"] += 1
            if calls["n"] < 3:
                raise ConnectionResetError("boom")
            return "ok"

        out = await redis_call_with_retry(flaky, s, "unit_op")
        assert out == "ok"
        assert calls["n"] == 3

    asyncio.run(body())


def test_monotonic_backoff_bounded() -> None:
    s = minimal_test_settings(redis_transport_backoff_sec=0.05, redis_transport_backoff_max_sec=1.0)
    for i in range(20):
        d = monotonic_backoff_sleep_sec(i, s)
        assert 0.0 <= d <= 1.5
