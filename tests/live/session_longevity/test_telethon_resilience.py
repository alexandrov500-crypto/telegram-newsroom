"""Telethon reconnect and session helpers (mocked; CI-safe)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from telethon.errors import FloodWaitError, RPCError

from collector.retry import ensure_connected, with_telethon_retries
from collector.telethon_client import build_telethon_client
from tests.conftest import minimal_test_settings
from utils.metrics import export_snapshot, reset_metrics


@pytest.fixture(autouse=True)
def _reset_metrics() -> None:
    reset_metrics()
    yield
    reset_metrics()


def test_ensure_connected_increments_reconnect_metric() -> None:
    async def body() -> None:
        client = MagicMock()
        client.is_connected.return_value = False
        client.connect = AsyncMock()
        await ensure_connected(client)
        snap = export_snapshot()
        assert int(snap["counters"]["telethon_reconnects"]) >= 1

    asyncio.run(body())


def test_floodwait_waits_bounded() -> None:
    async def body() -> None:
        sleeps: list[float] = []
        real_sleep = asyncio.sleep

        async def track_sleep(sec: float) -> None:
            sleeps.append(sec)
            await real_sleep(0)

        import collector.retry as cr

        original = cr.asyncio.sleep
        cr.asyncio.sleep = track_sleep
        try:
            calls = 0

            async def flaky() -> str:
                nonlocal calls
                calls += 1
                if calls < 2:
                    raise FloodWaitError(request=None, capture=2)  # type: ignore[arg-type]
                return "ok"

            out = await with_telethon_retries("test", flaky, max_attempts=3, base_delay_s=0.1)
            assert out == "ok"
            assert sleeps and sleeps[0] >= 0.1
        finally:
            cr.asyncio.sleep = original

    asyncio.run(body())


def test_session_sqlite_path_client_builds(tmp_path) -> None:
    s = minimal_test_settings(telethon_session_path=str(tmp_path / "live_test.session"))

    async def body() -> None:
        client = build_telethon_client(
            api_id=s.telegram_api_id,
            api_hash=s.telegram_api_hash,
            session_path=s.telethon_session_path,
        )
        assert client is not None

    asyncio.run(body())


def test_rpc_transient_retries_then_ok() -> None:
    async def body() -> None:
        import collector.retry as cr

        async def instant_sleep(_: float) -> None:
            return None

        cr.asyncio.sleep = instant_sleep
        n = 0

        async def flaky() -> int:
            nonlocal n
            n += 1
            if n < 2:
                raise RPCError(request=None, message="timeout", code=500)  # type: ignore[arg-type]
            return 42

        assert await with_telethon_retries("rpc", flaky, max_attempts=3) == 42

    asyncio.run(body())
