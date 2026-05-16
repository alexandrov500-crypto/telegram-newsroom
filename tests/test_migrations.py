from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
ALEMBIC_INI = REPO / "alembic.ini"


@pytest.mark.skipif(not ALEMBIC_INI.is_file(), reason="alembic.ini missing")
def test_alembic_upgrade_downgrade_cycle(tmp_path) -> None:
    db = tmp_path / "mig.db"
    url = f"sqlite:///{db}"
    env = os.environ.copy()
    env["DATABASE_URL"] = url
    env["PYTHONPATH"] = str(REPO)

    def run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), *args],
            cwd=str(REPO),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )

    r1 = run("upgrade", "head")
    assert r1.returncode == 0, r1.stderr + r1.stdout
    con = sqlite3.connect(str(db))
    try:
        tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()
    assert "drafts" in tables and "raw_posts" in tables and "published_posts" in tables

    r2 = run("downgrade", "base")
    assert r2.returncode == 0, r2.stderr
    con = sqlite3.connect(str(db))
    try:
        tables2 = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()
    assert "drafts" not in tables2

    r3 = run("upgrade", "head")
    assert r3.returncode == 0, r3.stderr
    r4 = run("upgrade", "head")
    assert r4.returncode == 0
