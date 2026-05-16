"""Semantics guardrails tool."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from tools.semantics_guardrails import run_guardrails

REPO = Path(__file__).resolve().parents[2]


def test_guardrails_repo_ok() -> None:
    r = run_guardrails(repo=REPO)
    assert r["read_only"] is True
    assert not any(f["code"] == "missing_semantics_doc" for f in r["findings"])


def test_cli_runs() -> None:
    proc = subprocess.run(
        [sys.executable, str(REPO / "tools/semantics_guardrails.py")],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0
    data = json.loads(proc.stdout)
    assert data["advisory_only"] is True
