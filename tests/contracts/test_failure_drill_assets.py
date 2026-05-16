"""Failure drill fixtures and frozen artifact guardrails."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from observability.runtime_contracts import FROZEN_ARTIFACT_FILENAMES, INSPECTION_CLI_COMMANDS

REPO = Path(__file__).resolve().parents[2]

DRILL_DIRS = (
    "broken_checksum",
    "missing_required",
    "invalid_schema",
    "warning_optional_missing",
    "missing_bundle",
)

FORBIDDEN_NEW_RUNTIME_JSON = (
    "runtime_telemetry.json",
    "governance_report.json",
    "orchestration_graph.json",
)


@pytest.mark.parametrize("name", DRILL_DIRS)
def test_failure_drill_directory_exists(name: str) -> None:
    base = REPO / "examples/failure_drills" / name
    assert base.is_dir(), name
    assert (base / "README.md").is_file()
    assert (base / "runtime").is_dir()


def test_failure_drills_root_readme() -> None:
    assert (REPO / "examples/failure_drills/README.md").is_file()


@pytest.mark.parametrize("name", DRILL_DIRS)
def test_drill_runtime_only_frozen_filenames(name: str) -> None:
    rt = REPO / "examples/failure_drills" / name / "runtime"
    for path in rt.glob("*.json"):
        assert path.name in FROZEN_ARTIFACT_FILENAMES, f"{name}: unexpected {path.name}"


def test_no_forbidden_new_artifact_names_in_drills() -> None:
    for name in FORBIDDEN_NEW_RUNTIME_JSON:
        assert name not in FROZEN_ARTIFACT_FILENAMES


@pytest.mark.parametrize("name", ("broken_checksum", "invalid_schema"))
def test_drill_json_readable(name: str) -> None:
    rt = REPO / "examples/failure_drills" / name / "runtime"
    for path in rt.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict)


def test_broken_checksum_triggers_verify_fail() -> None:
    import subprocess
    import sys

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "newsroom.cli",
            "verify-runtime",
            "--path",
            str(REPO / "examples/failure_drills/broken_checksum"),
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "checksum_mismatches" in proc.stdout


def test_frozen_cli_count_unchanged() -> None:
    assert len(INSPECTION_CLI_COMMANDS) == 11
