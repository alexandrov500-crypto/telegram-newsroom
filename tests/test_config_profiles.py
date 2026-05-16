from __future__ import annotations

import pytest

from tests.conftest import minimal_test_settings


def test_production_profile_tightens_defaults(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("APP_DEPLOYMENT_PROFILE", "production")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("BOT_TOKEN", "1:abc")
    monkeypatch.setenv("TELETHON_SESSION_STRING", "sess")
    monkeypatch.setenv("TELEGRAM_API_ID", "1")
    monkeypatch.setenv("TELEGRAM_API_HASH", "0123456789abcdef0123456789ab")
    monkeypatch.setenv("ADMIN_USER_ID", "1")
    monkeypatch.setenv("TARGET_CHANNEL_ID", "-100")
    monkeypatch.setenv("SOURCE_CHANNELS", "@c")
    dbf = tmp_path / "prod_profile.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{dbf}")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    from app.config import load_settings

    s = load_settings()
    assert s.deployment_profile == "production"
    assert s.log_level != "DEBUG"
    assert s.telegram_inter_chunk_delay_sec >= 0.45
    assert s.publish_channel_min_interval_sec >= 0.75


def test_development_profile_default() -> None:
    s = minimal_test_settings()
    assert s.deployment_profile == "development"
