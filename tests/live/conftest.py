"""Live Telegram validation fixtures (bounded + opt-in live)."""

from __future__ import annotations

import os

import pytest


def live_telegram_enabled() -> bool:
    return os.environ.get("TELEGRAM_LIVE_VALIDATE", "").strip().lower() in {"1", "true", "yes", "on"}


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "live_telegram: opt-in real Telegram API tests (TELEGRAM_LIVE_VALIDATE=1 + credentials)",
    )


@pytest.fixture
def live_telegram_guard() -> None:
    if not live_telegram_enabled():
        pytest.skip("Set TELEGRAM_LIVE_VALIDATE=1 with valid .env to run live Telegram tests")
