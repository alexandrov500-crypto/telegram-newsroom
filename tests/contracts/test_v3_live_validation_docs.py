"""v3 live Telegram validation contracts."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

LIVE_DOCS = (
    "docs/live_validation/live_telegram_validation_plan.md",
    "docs/live_validation/operator_workflow_validation.md",
    "docs/live_validation/live_validation_governance.md",
    "docs/v3_live_telegram_validation_report.md",
)


@pytest.mark.parametrize("rel", LIVE_DOCS)
def test_live_validation_docs_exist(rel: str) -> None:
    assert (REPO / rel).is_file(), rel


def test_live_telegram_diagnostics_tool() -> None:
    assert (REPO / "tools/live_telegram_diagnostics.py").is_file()
    proc = subprocess.run(
        [sys.executable, str(REPO / "tools/live_telegram_diagnostics.py")],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data.get("read_only") is True
    assert data.get("no_telegram_api_calls") is True


def test_live_tests_bounded_default() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/live",
            "-q",
            "--tb=short",
            "-m",
            "not live_telegram",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
