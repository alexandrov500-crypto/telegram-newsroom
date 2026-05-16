from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
HEALTHCHECK = REPO / "docker" / "healthcheck.py"


def _valid_healthcheck_env(tmp_path: Path) -> dict[str, str]:
    db = tmp_path / "subprocess_hc.db"
    return {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(REPO),
        "PYTHONNOUSERSITE": "1",
        "HOME": str(tmp_path),
        "OPENAI_API_KEY": "sk-test-placeholder-not-a-real-secret",
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
        "DRY_RUN": "1",
    }


@pytest.mark.skipif(not HEALTHCHECK.is_file(), reason="healthcheck script missing")
def test_healthcheck_subprocess_exit_zero(tmp_path):
    env = _valid_healthcheck_env(tmp_path)
    proc = subprocess.run(
        [sys.executable, str(HEALTHCHECK)],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout


@pytest.mark.skipif(not HEALTHCHECK.is_file(), reason="healthcheck script missing")
def test_healthcheck_subprocess_invalid_admin_exit_nonzero(tmp_path):
    env = _valid_healthcheck_env(tmp_path)
    env["ADMIN_USER_ID"] = "0"
    proc = subprocess.run(
        [sys.executable, str(HEALTHCHECK)],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode != 0
