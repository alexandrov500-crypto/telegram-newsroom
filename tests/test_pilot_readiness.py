from __future__ import annotations

import os
from pathlib import Path

from bot.live_ops.pilot_readiness import evaluate_pilot_db, evaluate_pilot_env
from bot.storage.db import init_database


def test_pilot_env_canary(monkeypatch) -> None:
    monkeypatch.setenv("CONTROLLED_LIVE_ENABLED", "true")
    monkeypatch.setenv("LIVE_MODE", "canary")
    monkeypatch.setenv("LIVE_PUBLIC_CHANNEL_ID", "-100123")
    monkeypatch.setenv("LIVE_OPS_CHANNEL_ID", "-100456")
    monkeypatch.setenv("BOT_TOKEN", "test")
    monkeypatch.setenv("SHADOW_PUBLISH_ONLY", "false")
    report = evaluate_pilot_env()
    assert report.ready


def test_pilot_env_blocks_autonomous(monkeypatch) -> None:
    monkeypatch.setenv("CONTROLLED_LIVE_ENABLED", "true")
    monkeypatch.setenv("LIVE_MODE", "autonomous_live")
    monkeypatch.setenv("LIVE_PUBLIC_CHANNEL_ID", "-100123")
    monkeypatch.setenv("LIVE_OPS_CHANNEL_ID", "-100456")
    monkeypatch.setenv("BOT_TOKEN", "test")
    report = evaluate_pilot_env()
    assert not report.ready


def test_pilot_db_tables(tmp_path: Path) -> None:
    init_database(tmp_path / "pr.db")
    report = evaluate_pilot_db(tmp_path / "pr.db")
    assert report.ready
