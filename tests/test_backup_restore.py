from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
BACKUP_CLI = REPO / "tools" / "backup_cli.py"


def _env(tmp: Path, db: Path) -> dict[str, str]:
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
        "RUNTIME_STATE_DIR": str(tmp / "rt"),
        "NEWSROOM_BACKUP_DIR": str(tmp / "backups"),
        "DRY_RUN": "1",
    }


@pytest.mark.skipif(not BACKUP_CLI.is_file(), reason="backup_cli missing")
def test_backup_create_validate_roundtrip(tmp_path) -> None:
    db = tmp_path / "n.db"
    import asyncio

    from db.session import close_db, init_db

    asyncio.run(close_db())
    asyncio.run(init_db(f"sqlite+aiosqlite:///{db}"))
    asyncio.run(close_db())

    env = _env(tmp_path, db)
    proc = subprocess.run(
        [sys.executable, str(BACKUP_CLI), "backup-create"],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert proc.returncode == 0, proc.stderr
    zpath = Path(proc.stdout.strip())
    assert zpath.is_file()

    v = subprocess.run(
        [sys.executable, str(BACKUP_CLI), "backup-validate", str(zpath)],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert v.returncode == 0, v.stderr

    with zipfile.ZipFile(zpath, "r") as zf:
        meta = json.loads(zf.read("metadata.json").decode("utf-8"))
    assert "metrics_counters" in meta
    assert "editorial_analytics" in meta
