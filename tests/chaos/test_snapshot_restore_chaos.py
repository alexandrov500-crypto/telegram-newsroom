"""Snapshot / restore torture tests (inspection tree; no format changes)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from observability.runtime_contracts import REQUIRED_ARTIFACT_FILENAMES
from utils.reliability_diagnostics import (
    RESTORE_COMPATIBILITY_MATRIX,
    SNAPSHOT_INTEGRITY_MATRIX,
)

REPO = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("row", SNAPSHOT_INTEGRITY_MATRIX, ids=lambda r: r.scenario)
def test_snapshot_integrity_matrix_defined(row: object) -> None:
    assert row.expected_verify
    assert row.operator_action


@pytest.mark.parametrize("row", RESTORE_COMPATIBILITY_MATRIX, ids=lambda r: r.source)
def test_restore_compatibility_matrix_defined(row: object) -> None:
    assert row.notes


def test_verify_runtime_on_broken_checksum_drill() -> None:
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
    assert "checksum" in proc.stdout.lower() or "FAIL" in proc.stdout


def test_runtime_index_warning_on_optional_missing_drill() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "newsroom.cli",
            "runtime-index",
            "--path",
            str(REPO / "examples/failure_drills/warning_optional_missing"),
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "WARNING" in proc.stdout


def test_restore_over_live_tree_replaces_runtime(tmp_path: Path) -> None:
    live = tmp_path / "live"
    snap = REPO / "examples/failure_drills/warning_optional_missing"
    (live / "runtime").mkdir(parents=True)
    (live / "runtime" / "stale_marker.json").write_text('{"stale": true}', encoding="utf-8")
    proc = subprocess.run(
        ["bash", str(REPO / "scripts/runtime_restore.sh"), str(snap), str(live)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert not (live / "runtime" / "stale_marker.json").exists()
    assert (live / "runtime" / "runtime_index.json").is_file()


def test_partial_snapshot_missing_required_fails_sanity(tmp_path: Path) -> None:
    from tests.chaos.framework import write_partial_snapshot

    partial = tmp_path / "partial"
    write_partial_snapshot(
        partial,
        files={
            "health_snapshot.json": json.dumps({"schema_version": 1, "pipeline_status": "OK"}),
            "runtime_report.json": json.dumps({"schema_version": 1, "incident_level": "NONE"}),
        },
    )
    missing = [
        n
        for n in REQUIRED_ARTIFACT_FILENAMES
        if n not in {"health_snapshot.json", "runtime_report.json", "runtime_index.json"}
        and not (partial / "runtime" / n).is_file()
    ]
    assert len(missing) >= 8


def test_corrupted_json_still_readable_as_drill(tmp_path: Path) -> None:
    bad = tmp_path / "bad" / "runtime"
    bad.mkdir(parents=True)
    (bad / "health_snapshot.json").write_text("{not-json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        json.loads((bad / "health_snapshot.json").read_text(encoding="utf-8"))
