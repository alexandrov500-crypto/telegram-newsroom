from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.dependency_state import DependencyStatus, reset_dependency_state
from app.telegram_polling import (
    classify_telegram_failure,
    polling_backoff_sec,
    run_connectivity_probe,
    run_polling_supervisor,
    set_telegram_api_runtime,
)


def test_polling_backoff_growth() -> None:
    assert polling_backoff_sec(1) == 5.0
    assert polling_backoff_sec(2) == 10.0
    assert polling_backoff_sec(3) == 20.0
    assert polling_backoff_sec(4) == 30.0
    assert polling_backoff_sec(99) == 30.0


def test_classify_unauthorized_unavailable() -> None:
    pytest.importorskip("aiogram")
    from aiogram.exceptions import TelegramUnauthorizedError

    assert classify_telegram_failure(TelegramUnauthorizedError("bad", "m")) == DependencyStatus.UNAVAILABLE


def test_connectivity_probe_recovers_after_timeout() -> None:
    pytest.importorskip("aiogram")
    reset_dependency_state()
    calls = {"n": 0}

    async def get_me():
        calls["n"] += 1
        if calls["n"] < 2:
            raise TimeoutError()
        m = MagicMock()
        m.id = 99
        m.username = "probebot"
        return m

    bot = MagicMock()
    bot.get_me = get_me
    settings = MagicMock()
    settings.healthcheck_timeout_sec = 2.0

    with patch("app.telegram_polling.asyncio.sleep", new_callable=AsyncMock):
        status = asyncio.run(run_connectivity_probe(bot, settings))

    assert status == DependencyStatus.HEALTHY
    assert calls["n"] == 2
    deps = __import__("app.dependency_state", fromlist=["get_dependency_state"]).get_dependency_state()
    assert deps.telegram_api.status == DependencyStatus.HEALTHY


def test_supervisor_retries_on_network_error_without_exit() -> None:
    pytest.importorskip("aiogram")
    from aiogram.exceptions import TelegramNetworkError

    reset_dependency_state()
    poll_calls = {"n": 0}
    shutdown = asyncio.Event()

    async def fake_polling(*args, **kwargs):
        poll_calls["n"] += 1
        if poll_calls["n"] == 1:
            raise TelegramNetworkError(method=MagicMock(), message="Request timeout error")
        shutdown.set()

    bot = MagicMock()
    bot.delete_webhook = AsyncMock()
    me = MagicMock(id=1, username="x")
    bot.get_me = AsyncMock(return_value=me)

    dp = MagicMock()
    dp.resolve_used_update_types = MagicMock(return_value=[])
    dp.start_polling = AsyncMock(side_effect=fake_polling)
    dp.stop_polling = AsyncMock()

    settings = MagicMock()
    settings.healthcheck_timeout_sec = 5.0

    with patch("app.telegram_polling.asyncio.sleep", new_callable=AsyncMock):
        asyncio.run(run_polling_supervisor(bot, dp, settings, shutdown_event=shutdown))

    assert poll_calls["n"] >= 2
    deps = __import__("app.dependency_state", fromlist=["get_dependency_state"]).get_dependency_state()
    assert deps.polling_retry_count == 0 or deps.telegram_api.status in (
        DependencyStatus.HEALTHY,
        DependencyStatus.DEGRADED,
    )


def test_health_degraded_during_retry() -> None:
    reset_dependency_state()
    set_telegram_api_runtime(
        status=DependencyStatus.DEGRADED,
        detail="Request timeout error",
        polling_active=False,
        retry_count=3,
    )
    from app.dependency_state import get_dependency_state

    payload = get_dependency_state().health_payload()
    assert payload["status"] == "degraded"
    assert payload["dependencies"]["telegram_api"]["retry_count"] == 3
    assert payload["dependencies"]["telegram_api"]["polling_active"] is False


def test_health_healthy_when_polling_active() -> None:
    reset_dependency_state()
    set_telegram_api_runtime(
        status=DependencyStatus.HEALTHY,
        detail="polling",
        polling_active=True,
        retry_count=0,
    )
    from app.dependency_state import get_dependency_state

    payload = get_dependency_state().health_payload()
    assert payload["dependencies"]["telegram_api"]["polling_active"] is True
    assert payload["dependencies"]["telegram_api"]["status"] == "healthy"
