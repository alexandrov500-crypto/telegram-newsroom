from __future__ import annotations

import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.runtime_notifications import (
    PROCESS_RUNTIME_UUID,
    maybe_send_polling_recovery_notification,
    maybe_send_process_startup_notification,
    reset_notification_state_for_tests,
)
from tests.conftest import minimal_test_settings


def test_startup_sent_only_once_per_process() -> None:
    reset_notification_state_for_tests()
    bot = MagicMock()
    bot.send_message = AsyncMock()
    settings = minimal_test_settings(send_startup_notification=True, notification_rate_limit_minutes=0)

    assert asyncio.run(maybe_send_process_startup_notification(bot, settings)) is True
    assert asyncio.run(maybe_send_process_startup_notification(bot, settings)) is False
    assert bot.send_message.await_count == 1
    text = bot.send_message.await_args.args[1]
    assert "Newsroom started" in text
    assert "runtime_dir=" in text


def test_polling_recovery_does_not_send_startup_banner() -> None:
    reset_notification_state_for_tests()
    bot = MagicMock()
    bot.send_message = AsyncMock()
    settings = minimal_test_settings(
        send_startup_notification=True,
        send_recovery_notification=False,
    )

    asyncio.run(
        maybe_send_polling_recovery_notification(bot, settings, cause="network", retry_count=2)
    )
    bot.send_message.assert_not_called()


def test_recovery_notification_when_enabled_and_rate_limit_allows() -> None:
    reset_notification_state_for_tests()
    bot = MagicMock()
    bot.send_message = AsyncMock()
    settings = minimal_test_settings(
        send_startup_notification=False,
        send_recovery_notification=True,
        notification_rate_limit_minutes=0,
    )

    assert asyncio.run(
        maybe_send_polling_recovery_notification(bot, settings, cause="network", retry_count=1)
    )
    text = bot.send_message.await_args.args[1]
    assert "polling recovered" in text
    assert "Newsroom started" not in text


def test_recovery_notification_rate_limited() -> None:
    reset_notification_state_for_tests()
    bot = MagicMock()
    bot.send_message = AsyncMock()
    settings = minimal_test_settings(
        send_recovery_notification=True,
        notification_rate_limit_minutes=60,
    )

    with patch("app.runtime_notifications.time.monotonic", return_value=100.0):
        assert asyncio.run(
            maybe_send_polling_recovery_notification(bot, settings, cause="network")
        )
        assert bot.send_message.await_count == 1
        assert (
            asyncio.run(
                maybe_send_polling_recovery_notification(bot, settings, cause="network")
            )
            is False
        )
        assert bot.send_message.await_count == 1


def test_supervisor_retry_skips_startup_notification() -> None:
    """Simulate second call as if polling reconnected — must not resend startup."""
    pytest.importorskip("aiogram")
    from aiogram.exceptions import TelegramNetworkError

    reset_notification_state_for_tests()
    send_calls: list[str] = []

    async def capture_send(chat_id, text, **kwargs):
        send_calls.append(text)

    bot = MagicMock()
    bot.send_message = capture_send
    bot.delete_webhook = AsyncMock()
    wh = MagicMock(url="", pending_update_count=0, last_error_date=None, last_error_message=None, max_connections=None)
    bot.get_webhook_info = AsyncMock(return_value=wh)
    me = MagicMock(id=1, username="x")
    bot.get_me = AsyncMock(return_value=me)

    settings = minimal_test_settings(
        send_startup_notification=True,
        send_recovery_notification=False,
        notification_rate_limit_minutes=0,
    )
    asyncio.run(maybe_send_process_startup_notification(bot, settings))
    assert any("Newsroom started" in t for t in send_calls)
    send_calls.clear()

    from app.telegram_polling import run_polling_supervisor

    shutdown = asyncio.Event()
    poll_calls = {"n": 0}

    async def fake_polling(*args, **kwargs):
        poll_calls["n"] += 1
        if poll_calls["n"] == 1:
            raise TelegramNetworkError(method=MagicMock(), message="timeout")
        shutdown.set()

    dp = MagicMock()
    dp.resolve_used_update_types = MagicMock(return_value=[])
    dp.start_polling = AsyncMock(side_effect=fake_polling)
    dp.stop_polling = AsyncMock()

    with patch("app.telegram_polling.asyncio.sleep", new_callable=AsyncMock):
        with patch("app.telegram_polling.register_conflict_log_handler"):
            with patch(
                "app.telegram_polling.ensure_webhook_cleared_with_verify",
                new_callable=AsyncMock,
                return_value=True,
            ):
                asyncio.run(run_polling_supervisor(bot, dp, settings, shutdown_event=shutdown))

    assert poll_calls["n"] >= 2
    assert not any("Newsroom started" in t for t in send_calls)


def test_process_runtime_uuid_stable_in_process() -> None:
    assert PROCESS_RUNTIME_UUID
    assert len(PROCESS_RUNTIME_UUID) >= 8


def test_simulated_runtime_restart_sends_startup_again(tmp_path) -> None:
    """New process boot: in-process gate cleared; file lock released between boots."""
    from app.ops.runtime.active_runtime import register_active_runtime
    import os

    reset_notification_state_for_tests()
    bot = MagicMock()
    bot.send_message = AsyncMock()
    rd = str(tmp_path / "runtime")
    settings = minimal_test_settings(
        send_startup_notification=True,
        notification_rate_limit_minutes=0,
        runtime_state_dir=rd,
    )
    register_active_runtime(rd, runtime_id="test-a", pid=os.getpid())

    assert asyncio.run(maybe_send_process_startup_notification(bot, settings)) is True
    reset_notification_state_for_tests()
    register_active_runtime(rd, runtime_id="test-b", pid=os.getpid())
    assert asyncio.run(maybe_send_process_startup_notification(bot, settings)) is True
    assert bot.send_message.await_count == 2


def test_persisted_startup_rate_limit_blocks_restart_notification() -> None:
    from app.runtime_notifications import apply_persisted_notification_state

    reset_notification_state_for_tests()
    apply_persisted_notification_state(last_startup_notification_at_unix=__import__("time").time())
    bot = MagicMock()
    bot.send_message = AsyncMock()
    settings = minimal_test_settings(
        send_startup_notification=True,
        notification_rate_limit_minutes=60,
    )

    assert asyncio.run(maybe_send_process_startup_notification(bot, settings)) is False
    bot.send_message.assert_not_called()
