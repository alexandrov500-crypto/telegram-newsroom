"""Staging sign-off and v3.1 rollout documentation contracts."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

STAGING_DOCS = (
    "docs/staging/staging_environment_checklist.md",
    "docs/staging/live_staging_signoff.md",
    "docs/staging/operator_staging_signoff.md",
    "docs/staging/failure_injection_results.md",
)

OPS_ROLLOUT_DOCS = (
    "docs/operations/production_lite_rollout.md",
    "docs/operations/observability_validation.md",
    "docs/releases/v3.1-production-lite.md",
)


@pytest.mark.parametrize("rel", STAGING_DOCS + OPS_ROLLOUT_DOCS)
def test_staging_rollout_docs_exist(rel: str) -> None:
    assert (REPO / rel).is_file(), rel


def test_staging_environment_verify_tool() -> None:
    assert (REPO / "tools/staging_environment_verify.py").is_file()
    proc = subprocess.run(
        [sys.executable, str(REPO / "tools/staging_environment_verify.py")],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=60,
    )
    data = json.loads(proc.stdout)
    assert data.get("read_only") is True
    assert data.get("no_telegram_api_calls") is True


def test_bounded_failure_injection_suite() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/staging", "-q", "--tb=short"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
