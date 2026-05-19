from __future__ import annotations

import os
from unittest.mock import patch

from bot.operations.staging_env_validation import validate_staging_environment


def test_staging_env_passes_when_fully_configured() -> None:
    from bot.settings import BotSettings

    settings = BotSettings(
        TELEGRAM_BOT_TOKEN="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij",
        STAGING_MODE=True,
        SHADOW_PUBLISH_ONLY=True,
        AUTO_APPROVAL_ENABLED=False,
        STAGING_STRICT_STARTUP=True,
        TELEGRAM_OPERATOR_CHAT_ID=-1001234567890,
        TELEGRAM_DIGEST_CHANNEL_ID=-1009876543210,
        TELEGRAM_LIVE_INGEST_ENABLED=True,
        TELEGRAM_LIVE_COGNITIVE_ENABLED=True,
        TELEGRAM_LIVE_BURNIN_HOURLY=True,
        TELEGRAM_LIVE_APPROVAL_CARDS=True,
        ADMIN_USER_IDS="12345",
    )
    with patch.dict(
        os.environ,
        {
            "OPS_BURNIN_ENABLED": "true",
            "OPS_BURNIN_PROFILE": "24h",
            "REDIS_ENABLED": "true",
            "REDIS_URL": "redis://redis:6379/0",
            "DATABASE_URL": "postgresql+asyncpg://newsroom:newsroom@postgres:5432/newsroom",
        },
        clear=False,
    ):
        report = validate_staging_environment(settings)
    assert report.passed, report.operator_summary()


def test_staging_env_fails_missing_operator_chat() -> None:
    from bot.settings import BotSettings

    settings = BotSettings(
        TELEGRAM_BOT_TOKEN="123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij",
        STAGING_MODE=True,
        SHADOW_PUBLISH_ONLY=True,
        AUTO_APPROVAL_ENABLED=False,
    )
    report = validate_staging_environment(settings)
    assert not report.passed
    assert "TELEGRAM_OPERATOR_CHAT_ID" in report.failed_names()
