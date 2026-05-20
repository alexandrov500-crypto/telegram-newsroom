from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

from app.dependency_state import DependencyStatus, reset_dependency_state
from app.telegram_runtime import (
    TelegramConflictLogHandler,
    ensure_webhook_cleared_with_verify,
    inspect_webhook,
    record_polling_conflict,
    register_conflict_log_handler,
)
from tests.conftest import minimal_test_settings


def test_conflict_log_handler_sets_degraded() -> None:
    reset_dependency_state()
    handler = TelegramConflictLogHandler()
    record = logging.LogRecord(
        name="aiogram.dispatcher",
        level=logging.ERROR,
        pathname="",
        lineno=0,
        msg="Failed to fetch updates - TelegramConflictError: Conflict: terminated by other getUpdates request",
        args=(),
        exc_info=None,
    )
    handler.emit(record)
    deps = __import__("app.dependency_state", fromlist=["get_dependency_state"]).get_dependency_state()
    assert deps.conflict_detected is True
    assert deps.telegram_api.status == DependencyStatus.DEGRADED


def test_webhook_inspect_and_delete() -> None:
    reset_dependency_state()

    info_before = MagicMock()
    info_before.url = "https://example.com/hook"
    info_before.pending_update_count = 2
    info_before.last_error_date = None
    info_before.last_error_message = None
    info_before.max_connections = 40

    info_after = MagicMock()
    info_after.url = ""
    info_after.pending_update_count = 0
    info_after.last_error_date = None
    info_after.last_error_message = None
    info_after.max_connections = 40

    bot = MagicMock()
    bot.get_webhook_info = AsyncMock(side_effect=[info_before, info_after])
    bot.delete_webhook = AsyncMock()

    cleared = asyncio.run(ensure_webhook_cleared_with_verify(bot))
    assert cleared is True
    bot.delete_webhook.assert_called_once_with(drop_pending_updates=True)


def test_inspect_webhook_logs_info() -> None:
    info = MagicMock()
    info.url = ""
    info.pending_update_count = 0
    info.last_error_date = None
    info.last_error_message = None
    info.max_connections = None
    bot = MagicMock()
    bot.get_webhook_info = AsyncMock(return_value=info)
    fields = asyncio.run(inspect_webhook(bot))
    assert fields["webhook_url"] == ""


def test_health_v2_telegram_api_conflict_fields() -> None:
    reset_dependency_state()
    deps = __import__("app.dependency_state", fromlist=["get_dependency_state"]).get_dependency_state()
    record_polling_conflict(retry_count=2)
    deps.telegram_mode = "polling"
    deps.polling_instance_id = "test-uuid"
    deps.bot_id = 42
    deps.bot_username = "testbot"
    payload = deps.health_payload()
    tg = payload["dependencies"]["telegram_api"]
    assert tg["status"] == "degraded"
    assert tg["mode"] == "polling"
    assert tg["conflict_detected"] is True
    assert tg["polling_instance_id"] == "test-uuid"
    assert tg["bot_id"] == 42


def test_polling_disabled_setting() -> None:
    s = minimal_test_settings(telegram_polling_enabled=False)
    assert s.telegram_polling_enabled is False
