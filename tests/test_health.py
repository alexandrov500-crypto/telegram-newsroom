from __future__ import annotations

import asyncio
from dataclasses import replace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.startup_validation import validate_settings_for_launch
from tests.conftest import minimal_test_settings


class _FakeTelethonOk:
    def __init__(self) -> None:
        self._connected = False

    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def is_user_authorized(self) -> bool:
        return True


def test_validate_settings_passes_for_minimal(valid_settings):
    validate_settings_for_launch(valid_settings)


def test_validate_settings_fails_on_empty_openai_key(valid_settings):
    bad = replace(valid_settings, openai_api_key="")
    with pytest.raises(RuntimeError, match="Startup validation failed"):
        validate_settings_for_launch(bad)


def test_validate_settings_fails_on_invalid_bot_token(valid_settings):
    bad = replace(valid_settings, bot_token="not-a-token")
    with pytest.raises(RuntimeError, match="BOT_TOKEN"):
        validate_settings_for_launch(bad)


def test_validate_settings_fails_on_zero_admin(valid_settings):
    bad = replace(valid_settings, admin_user_id=0)
    with pytest.raises(RuntimeError, match="ADMIN_USER_ID"):
        validate_settings_for_launch(bad)


def test_validate_settings_fails_on_invalid_model(valid_settings):
    bad = replace(valid_settings, openai_model="bad model!")
    with pytest.raises(RuntimeError, match="OPENAI_MODEL"):
        validate_settings_for_launch(bad)


def test_run_startup_healthchecks_success(monkeypatch):
    pytest.importorskip("aiogram")
    pytest.importorskip("openai")
    from app.health import run_startup_healthchecks

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
    mock_bot.get_me = AsyncMock(return_value=MagicMock(id=1, username="testbot"))

    monkeypatch.setattr("app.health.build_telethon_client", lambda **kwargs: _FakeTelethonOk())

    settings = minimal_test_settings()

    async def main() -> None:
        await run_startup_healthchecks(settings, mock_bot, mock_openai, health_timeout_sec=5.0)

    asyncio.run(main())

    mock_engine.connect.assert_called()
    mock_openai.models.retrieve.assert_called_once()
    mock_bot.get_me.assert_called_once()


def test_run_startup_healthchecks_raises_on_db_failure(monkeypatch):
    pytest.importorskip("openai")
    from app.health import run_startup_healthchecks

    mock_engine = MagicMock()

    class BadCM:
        async def __aenter__(self):
            raise RuntimeError("db down")

        async def __aexit__(self, *args):
            return None

    mock_engine.connect = MagicMock(return_value=BadCM())
    monkeypatch.setattr("app.health.get_engine", lambda: mock_engine)

    mock_openai = MagicMock()
    mock_openai.models.retrieve = AsyncMock(return_value=MagicMock())
    mock_bot = MagicMock()
    mock_bot.get_me = AsyncMock(return_value=MagicMock(id=1, username="x"))

    monkeypatch.setattr("app.health.build_telethon_client", lambda **kwargs: _FakeTelethonOk())

    settings = minimal_test_settings()

    async def main() -> None:
        await run_startup_healthchecks(settings, mock_bot, mock_openai, health_timeout_sec=5.0)

    with pytest.raises(RuntimeError, match="Startup healthchecks failed"):
        asyncio.run(main())
