"""Session and limiter recovery (mocked, CI-safe)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from telethon.errors import RPCError, SessionPasswordNeededError

from collector.retry import ensure_connected, with_telethon_retries
from publisher.rate_limit import get_publish_rate_limiter, reset_publish_rate_limiter_for_tests
from tests.conftest import minimal_test_settings
from utils.metrics import export_snapshot, reset_metrics


@pytest.fixture(autouse=True)
def _reset_metrics() -> None:
    reset_metrics()
    yield
    reset_metrics()


def test_sqlite_session_build_with_missing_file_uses_new_path(tmp_path) -> None:
    """SQLite session path may not exist until first connect; build should not crash."""
    path = tmp_path / "new_session.session"

    async def body() -> None:
        from collector.telethon_client import build_telethon_client

        s = minimal_test_settings(telethon_session_path=str(path))
        client = build_telethon_client(
            api_id=s.telegram_api_id,
            api_hash=s.telegram_api_hash,
            session_path=s.telethon_session_path,
        )
        assert client is not None

    asyncio.run(body())


def test_invalid_auth_key_not_retried() -> None:
    async def body() -> None:
        async def op() -> None:
            raise SessionPasswordNeededError(request=MagicMock())  # type: ignore[arg-type]

        with pytest.raises(SessionPasswordNeededError):
            await with_telethon_retries("auth", op, max_attempts=4, base_delay_s=0.01)

    asyncio.run(body())


def test_reconnect_after_disconnect_restores_metric() -> None:
    async def body() -> None:
        client = MagicMock()
        client.is_connected.side_effect = [False, True]
        client.connect = AsyncMock()
        await ensure_connected(client)
        snap = export_snapshot()
        assert int(snap["counters"]["telethon_reconnects"]) >= 1

    asyncio.run(body())


def test_corrupted_session_connect_failure_surfaces() -> None:
    async def body() -> None:
        client = MagicMock()
        client.is_connected.return_value = False
        client.connect = AsyncMock(side_effect=OSError("session file corrupt"))

        with pytest.raises(OSError, match="corrupt"):
            await ensure_connected(client)

    asyncio.run(body())


def test_stale_rate_limiter_cleared_after_reset() -> None:
    reset_publish_rate_limiter_for_tests()
    t = {"now": 0.0}

    def clock() -> float:
        return t["now"]

    lim = get_publish_rate_limiter(
        min_interval_sec=0.0,
        burst_window_sec=10.0,
        burst_max_messages=1,
        clock=clock,
    )

    async def acquire() -> None:
        await lim.acquire_before_publish(99)

    asyncio.run(acquire())
    reset_publish_rate_limiter_for_tests()
    t["now"] = 0.0
    asyncio.run(acquire())


def test_floodwait_increments_metric() -> None:
    async def body() -> None:
        import collector.retry as cr

        original_sleep = cr.asyncio.sleep

        async def instant_sleep(_: float) -> None:
            return None

        cr.asyncio.sleep = instant_sleep
        calls = 0
        try:
            async def flaky() -> str:
                nonlocal calls
                calls += 1
                if calls < 2:
                    from telethon.errors import FloodWaitError

                    raise FloodWaitError(request=None, capture=1)  # type: ignore[arg-type]
                return "ok"

            await with_telethon_retries("fw", flaky, max_attempts=3, base_delay_s=0.1)
            snap = export_snapshot()
            assert int(snap["counters"].get("telethon_flood_waits", 0)) >= 1
        finally:
            cr.asyncio.sleep = original_sleep

    asyncio.run(body())


def test_rpc_auth_error_retries_until_exhausted() -> None:
    """401-class RPC errors follow transient path; exhaustion re-raises last error."""

    async def body() -> None:
        import collector.retry as cr

        cr.asyncio.sleep = AsyncMock()

        async def flaky() -> str:
            raise RPCError(request=None, message="AUTH_KEY_UNREGISTERED", code=401)  # type: ignore[arg-type]

        with pytest.raises(RPCError, match="AUTH_KEY"):
            await with_telethon_retries("reset", flaky, max_attempts=2, base_delay_s=0.01)

    asyncio.run(body())
