from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
CLI = REPO / "tools" / "admin_cli.py"


def _base_env(tmp: Path) -> dict[str, str]:
    db = tmp / "cli.db"
    return {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(REPO),
        "PYTHONNOUSERSITE": "1",
        "HOME": str(tmp),
        "OPENAI_API_KEY": "sk-test-placeholder",
        "OPENAI_MODEL": "gpt-4.1-mini",
        "BOT_TOKEN": "123456:TEST-token-placeholder",
        "TELETHON_SESSION_STRING": "test-session-string-placeholder",
        "TELEGRAM_API_ID": "123456",
        "TELEGRAM_API_HASH": "testhashplaceholder0123456789ab",
        "ADMIN_USER_ID": "1",
        "TARGET_CHANNEL_ID": "-1001234567890",
        "SOURCE_CHANNELS": "@testchannel",
        "DATABASE_URL": f"sqlite+aiosqlite:///{db}",
        "PIPELINE_INTERVAL_MINUTES": "30",
        "RUNTIME_STATE_DIR": str(tmp / "rt_cli"),
        "DRY_RUN": "1",
    }


@pytest.mark.skipif(not CLI.is_file(), reason="admin_cli missing")
def test_admin_cli_metrics_json(tmp_path, subprocess_timeout=60):
    env = _base_env(tmp_path)
    proc = subprocess.run(
        [sys.executable, str(CLI), "--json", "metrics"],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=subprocess_timeout,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert "counters" in data


@pytest.mark.skipif(not CLI.is_file(), reason="admin_cli missing")
def test_admin_cli_latest_snapshot_missing_ok(tmp_path):
    env = _base_env(tmp_path)
    proc = subprocess.run(
        [sys.executable, str(CLI), "latest-snapshot"],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0
    assert "no snapshot" in proc.stdout.lower()


@pytest.mark.skipif(not CLI.is_file(), reason="admin_cli missing")
def test_admin_cli_editorial_insights_json(tmp_path, subprocess_timeout=60):
    env = _base_env(tmp_path)
    proc = subprocess.run(
        [sys.executable, str(CLI), "--json", "editorial-insights"],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=subprocess_timeout,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert "pending_count" in data


@pytest.mark.skipif(not CLI.is_file(), reason="admin_cli missing")
def test_admin_cli_latest_snapshot_json_null(tmp_path):
    env = _base_env(tmp_path)
    proc = subprocess.run(
        [sys.executable, str(CLI), "--json", "latest-snapshot"],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() in {"null", "null\n"}
