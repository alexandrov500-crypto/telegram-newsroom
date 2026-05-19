from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from bot.operations.startup_validation import CHECK_ORDER, StartupValidationRunner
from bot.runtime.state import runtime_state
from bot.storage.db import init_database


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return init_database(tmp_path / "startup.db")


def test_check_order_is_stable() -> None:
    assert CHECK_ORDER[0] == "env.staging_live_flags"
    assert "env.telegram_token" in CHECK_ORDER
    assert "telegram.connectivity" in CHECK_ORDER


def test_startup_validation_passes_minimal(db_path: Path) -> None:
    from bot.config import load_settings

    with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test-token-1234567890"}, clear=False):
        settings = load_settings()
        runtime_state.staging_mode = False
        runtime_state.shadow_publish_only = False
        runtime_state.auto_approval_enabled = False
        report = StartupValidationRunner.run(
            settings=settings,
            db_path=db_path,
            rss_feed_count=2,
            node_role="operator",
        )
    assert report.fingerprint
    assert len(report.checks) == len(CHECK_ORDER)
    assert report.checks[0].check_id == "env.staging_live_flags"


def test_staging_requires_digest_channel(db_path: Path) -> None:
    from bot.config import load_settings

    env = {
        "TELEGRAM_BOT_TOKEN": "test-token-1234567890",
        "STAGING_MODE": "true",
        "SHADOW_PUBLISH_ONLY": "true",
        "AUTO_APPROVAL_ENABLED": "false",
    }
    with patch.dict(os.environ, env, clear=False):
        settings = load_settings()
        runtime_state.staging_mode = True
        runtime_state.shadow_publish_only = True
        runtime_state.auto_approval_enabled = False
        report = StartupValidationRunner.run(
            settings=settings,
            db_path=db_path,
            rss_feed_count=3,
            node_role="operator",
        )
    digest = next(c for c in report.checks if c.check_id == "env.staging_digest_channel")
    assert not digest.passed
    assert not report.passed


def test_fingerprint_is_deterministic(db_path: Path) -> None:
    from bot.config import load_settings

    with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test-token-1234567890"}, clear=False):
        settings = load_settings()
        runtime_state.staging_mode = False
        r1 = StartupValidationRunner.run(settings=settings, db_path=db_path, rss_feed_count=1)
        r2 = StartupValidationRunner.run(settings=settings, db_path=db_path, rss_feed_count=1)
    assert r1.fingerprint == r2.fingerprint


def test_run_smoke() -> None:
    with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "test-token-1234567890"}, clear=False):
        report = StartupValidationRunner.run_smoke()
    assert report.checks
    assert report.operator_summary().startswith("Startup validation")
