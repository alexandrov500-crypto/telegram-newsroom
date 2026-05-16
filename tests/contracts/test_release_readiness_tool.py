"""Release readiness tool contracts (read-only)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_release_readiness_default_ok() -> None:
    proc = subprocess.run(
        [sys.executable, str(REPO / "tools/release_readiness.py"), "--skip-pytest"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["read_only"] is True
    assert data["status"] == "OK"
    assert data["checks"]["runtime_contracts"] == "OK"


def test_release_readiness_strict_with_pytest() -> None:
    proc = subprocess.run(
        [sys.executable, str(REPO / "tools/release_readiness.py"), "--strict"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
