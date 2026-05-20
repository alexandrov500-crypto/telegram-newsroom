from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.dependency_state import AggregateStatus, DependencyStatus, reset_dependency_state
from app.health import run_startup_healthchecks
from tests.conftest import minimal_test_settings


class _FakeTelethonOk:
    async def connect(self) -> None:
        return None

    def is_connected(self) -> bool:
        return True

    async def disconnect(self) -> None:
        return None

    async def is_user_authorized(self) -> bool:
        return True


def test_openai_region_403_degraded_not_fatal(monkeypatch):
    pytest.importorskip("openai")
    from openai import PermissionDeniedError

    reset_dependency_state()
    monkeypatch.setattr("app.health.get_engine", lambda: MagicMock())

    class FakeConn:
        async def execute(self, *args, **kwargs):
            return None

    class ConnectCM:
        async def __aenter__(self):
            return FakeConn()

        async def __aexit__(self, *args):
            return None

    mock_engine = MagicMock()
    mock_engine.connect = MagicMock(return_value=ConnectCM())
    monkeypatch.setattr("app.health.get_engine", lambda: mock_engine)

    err_body = {
        "error": {
            "code": "unsupported_country_region_territory",
            "message": "Country, region, or territory not supported",
        }
    }
    mock_openai = MagicMock()
    mock_openai.models.retrieve = AsyncMock(
        side_effect=PermissionDeniedError("blocked", response=MagicMock(), body=err_body)
    )
    mock_bot = MagicMock()
    mock_bot.get_me = AsyncMock(return_value=MagicMock(id=1, username="bot"))
    monkeypatch.setattr("app.health.build_telethon_client", lambda **kwargs: _FakeTelethonOk())
    monkeypatch.setattr(
        "app.health._check_telethon",
        AsyncMock(return_value=DependencyStatus.HEALTHY),
    )

    settings = minimal_test_settings()

    async def main():
        return await run_startup_healthchecks(settings, mock_bot, mock_openai)

    result = asyncio.run(main())
    assert result.aggregate == AggregateStatus.DEGRADED
    assert result.ai_pipeline_enabled is False
    assert not result.fatal_errors


def test_telethon_missing_degraded(monkeypatch):
    reset_dependency_state()
    monkeypatch.setattr("app.health.get_engine", lambda: MagicMock())

    class FakeConn:
        async def execute(self, *args, **kwargs):
            return None

    class ConnectCM:
        async def __aenter__(self):
            return FakeConn()

        async def __aexit__(self, *args):
            return None

    mock_engine = MagicMock()
    mock_engine.connect = MagicMock(return_value=ConnectCM())
    monkeypatch.setattr("app.health.get_engine", lambda: mock_engine)

    mock_openai = MagicMock()
    mock_openai.models.retrieve = AsyncMock(return_value=MagicMock())
    mock_bot = MagicMock()
    mock_bot.get_me = AsyncMock(return_value=MagicMock(id=1, username="bot"))

    settings = minimal_test_settings(telethon_session_string="", telethon_session_path=None)

    async def main():
        return await run_startup_healthchecks(settings, mock_bot, mock_openai)

    result = asyncio.run(main())
    assert result.collector_enabled is False
    assert result.aggregate == AggregateStatus.DEGRADED
