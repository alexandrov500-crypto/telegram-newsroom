"""Smoke tests for offline recovery validation and replay inspection."""

from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from observability.runtime_manifest import (
    build_runtime_manifest,
    default_runtime_manifest_path,
    write_runtime_manifest,
)
from observability.runtime_recovery import (
    RECOVERY_KEY_ORDER,
    build_recovery_report,
    default_recovery_report_path,
    replay_runtime_inspection,
    strict_recovery_exit_code,
    validate_runtime_bundle,
    validate_runtime_recovery,
    validate_runtime_structure,
    write_recovery_report,
)
from utils.runtime_bundle import BUNDLE_DIR_NAME, write_runtime_bundle

REPO = Path(__file__).resolve().parents[2]


def _seed_full(od: Path) -> None:
    rt = od / "runtime"
    rt.mkdir(parents=True, exist_ok=True)
    (rt / "health_snapshot.json").write_text('{"pipeline_status":"OK"}', encoding="utf-8")
    (rt / "runtime_report.json").write_text('{"incident_level":"NONE"}', encoding="utf-8")
    manifest = build_runtime_manifest(output_dir=od)
    write_runtime_manifest(default_runtime_manifest_path(od), manifest)
    (od / "qualification.json").write_text('{"qualification_status":"OK"}', encoding="utf-8")
    (od / "ops_benchmark.json").write_text("{}", encoding="utf-8")


def _minimal_zip(path: Path) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{BUNDLE_DIR_NAME}/manifest.json", '{"bundle_version":"1"}')


def test_recovery_report_schema_and_key_order(tmp_path: Path) -> None:
    od = tmp_path / "out"
    _seed_full(od)
    _minimal_zip(od / "runtime_bundle.zip")

    report = validate_runtime_recovery(od)
    assert list(report.keys()) == list(RECOVERY_KEY_ORDER)
    assert report["recovery_status"] in ("OK", "WARNING")
    assert report["runtime_manifest_present"] is True
    assert "runtime/health_snapshot.json" in report["validated_paths"]


def test_deterministic_recovery_json_write(tmp_path: Path) -> None:
    od = tmp_path / "out"
    _seed_full(od)
    r1 = validate_runtime_recovery(od)
    r2 = validate_runtime_recovery(od)
    r1["generated_at"] = "2026-05-15T12:20:00Z"
    r2["generated_at"] = "2026-05-15T12:20:00Z"
    p = default_recovery_report_path(od)
    write_recovery_report(p, r1)
    write_recovery_report(p, r2)
    assert p.read_text(encoding="utf-8") == json.dumps(
        {k: r1[k] for k in RECOVERY_KEY_ORDER},
        indent=2,
        sort_keys=True,
        default=str,
    ) + "\n"


def test_missing_required_structure_fails(tmp_path: Path) -> None:
    od = tmp_path / "out"
    (od / "runtime").mkdir(parents=True)
    (od / "runtime" / "health_snapshot.json").write_text("{}", encoding="utf-8")

    structure = validate_runtime_structure(od)
    assert structure["runtime_structure_valid"] is False
    report = validate_runtime_recovery(od)
    assert report["recovery_status"] == "FAIL"
    assert report["required_artifacts_present"] is False


def test_invalid_zip_fails(tmp_path: Path) -> None:
    od = tmp_path / "out"
    _seed_full(od)
    (od / "runtime_bundle.zip").write_bytes(b"not-a-zip")

    bundle = validate_runtime_bundle(od, extract_dir=tmp_path / "extract")
    assert bundle["bundle_extractable"] is False
    report = validate_runtime_recovery(od)
    assert report["recovery_status"] == "FAIL"


def test_manifest_validation_integration(tmp_path: Path) -> None:
    od = tmp_path / "out"
    _seed_full(od)
    (od / "runtime" / "health_snapshot.json").write_text('{"tampered":true}', encoding="utf-8")

    report = validate_runtime_recovery(od)
    assert report["verification_status"] == "FAIL"
    assert report["recovery_status"] == "FAIL"


def test_bundle_extraction_validation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from dataclasses import replace

    od = tmp_path / "out"
    _seed_full(od)
    rd = tmp_path / "runtime_state"
    rd.mkdir()
    (rd / "soak_report.json").write_text('{"ok":true}', encoding="utf-8")

    class _Settings:
        runtime_state_dir = str(rd)
        redis_enabled = False

    write_runtime_bundle(rd, od / "runtime_bundle.zip", _Settings(), include_html=False)
    bundle = validate_runtime_bundle(od, extract_dir=tmp_path / "ext")
    assert bundle["bundle_extractable"] is True


def test_replay_temp_dir_cleanup(tmp_path: Path) -> None:
    od = tmp_path / "out"
    _seed_full(od)
    _minimal_zip(od / "runtime_bundle.zip")

    before = set(tmp_path.iterdir())
    result = replay_runtime_inspection(od)
    after = set(tmp_path.iterdir())

    assert result["replay"]["extracted_to_temp"] is True
    assert result["replay"]["pipeline_executed"] is False
    assert result["replay"]["inspection_only"] is True
    assert before == after


def test_strict_exit_codes() -> None:
    assert strict_recovery_exit_code({"recovery_status": "OK"}, strict=False) == 0
    assert strict_recovery_exit_code({"recovery_status": "WARNING"}, strict=True) == 1
    assert strict_recovery_exit_code({"recovery_status": "FAIL"}, strict=True) == 1


def test_cli_validate_recovery_strict(tmp_path: Path) -> None:
    od = tmp_path / "out"
    (od / "runtime").mkdir(parents=True)

    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "newsroom.cli",
            "validate-recovery",
            "--path",
            str(od),
            "--strict",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1


def test_cli_replay_runtime_smoke(tmp_path: Path) -> None:
    od = tmp_path / "out"
    _seed_full(od)
    _minimal_zip(od / "runtime_bundle.zip")

    proc = subprocess.run(
        [sys.executable, "-m", "newsroom.cli", "replay-runtime", "--path", str(od)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0
    assert "inspection-only" in proc.stdout.lower() or "Inspection-only" in proc.stdout


def test_missing_optional_recovery_warning(tmp_path: Path) -> None:
    od = tmp_path / "out"
    _seed_full(od)
    (od / "ops_benchmark.json").unlink()

    report = validate_runtime_recovery(od)
    assert report["recovery_status"] == "WARNING"
    assert report["required_artifacts_present"] is True
