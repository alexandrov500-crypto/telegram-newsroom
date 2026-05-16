"""Operational shell helper contracts (no new architecture)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

SHELL_SCRIPTS = (
    "scripts/runtime_snapshot.sh",
    "scripts/runtime_restore.sh",
    "scripts/runtime_sanity_check.sh",
)


@pytest.mark.parametrize("rel", SHELL_SCRIPTS)
def test_shell_scripts_exist_executable(rel: str) -> None:
    path = REPO / rel
    assert path.is_file(), rel
    assert path.stat().st_mode & 0o111, rel
    text = path.read_text(encoding="utf-8")
    assert "set -euo pipefail" in text


def test_shell_scripts_no_curl_or_orchestrator_keywords() -> None:
    for rel in SHELL_SCRIPTS:
        lower = (REPO / rel).read_text(encoding="utf-8").lower()
        assert "kubernetes" not in lower
        assert "celery" not in lower
        assert "while true" not in lower


def test_burn_in_docs_linked_from_start_here() -> None:
    text = (REPO / "docs/START_HERE.md").read_text(encoding="utf-8")
    assert "BURN_IN_REPORT.md" in text
    assert "FAILURE_DRILLS.md" in text
    assert "runtime_sanity_check.sh" in text


def test_docs_map_lists_burn_in() -> None:
    proc = subprocess.run(
        ["make", "-C", str(REPO), "docs-map"],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "BURN_IN_REPORT" in proc.stdout or "FAILURE_DRILLS" in proc.stdout


def test_maintenance_docs_exist_for_burn_in_phase() -> None:
    for rel in (
        "docs/BURN_IN_REPORT.md",
        "docs/FAILURE_DRILLS.md",
        "docs/RESTORE_PROCEDURE.md",
        "docs/KNOWN_LIMITATIONS.md",
    ):
        assert (REPO / rel).is_file(), rel


def test_sanity_check_on_warning_drill() -> None:
    proc = subprocess.run(
        ["bash", str(REPO / "scripts/runtime_sanity_check.sh")],
        cwd=str(REPO),
        env={
            **__import__("os").environ,
            "OUTPUT_DIR": str(REPO / "examples/failure_drills/warning_optional_missing"),
            "STRICT": "0",
        },
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "sanity: file checklist OK" in proc.stdout
