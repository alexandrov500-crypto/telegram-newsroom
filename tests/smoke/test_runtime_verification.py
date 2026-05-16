"""Smoke tests for offline runtime verification (no network)."""

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
from observability.runtime_verify import (
    VERIFY_KEY_ORDER,
    strict_verify_exit_code,
    verify_artifact_checksums,
    verify_required_artifacts,
    verify_runtime_manifest,
)
from utils.runtime_bundle import ZIP_FIXED_DTIME, write_runtime_bundle

REPO = Path(__file__).resolve().parents[2]


def _seed_required(od: Path) -> None:
    rt = od / "runtime"
    rt.mkdir(parents=True, exist_ok=True)
    (rt / "health_snapshot.json").write_text("{}", encoding="utf-8")
    (rt / "runtime_report.json").write_text("{}", encoding="utf-8")


def test_verify_ok_when_manifest_matches(tmp_path: Path) -> None:
    od = tmp_path / "out"
    _seed_required(od)
    (od / "qualification.json").write_text('{"qualification_status":"OK"}', encoding="utf-8")
    (od / "runtime_bundle.zip").write_bytes(b"bundle")
    (od / "ops_benchmark.json").write_text("{}", encoding="utf-8")
    manifest = build_runtime_manifest(output_dir=od)
    write_runtime_manifest(default_runtime_manifest_path(od), manifest)

    result = verify_runtime_manifest(output_dir=od)
    assert list(result.keys()) == list(VERIFY_KEY_ORDER)
    assert result["verification_status"] == "OK"
    assert result["missing_required"] == []
    assert result["checksum_mismatches"] == []


def test_missing_required_fails(tmp_path: Path) -> None:
    od = tmp_path / "out"
    (od / "runtime").mkdir(parents=True)
    manifest = build_runtime_manifest(output_dir=od)
    write_runtime_manifest(default_runtime_manifest_path(od), manifest)

    result = verify_runtime_manifest(output_dir=od)
    assert result["verification_status"] == "FAIL"
    assert "health_snapshot.json" in result["missing_required"]
    assert "runtime_report.json" in result["missing_required"]


def test_checksum_mismatch_fails(tmp_path: Path) -> None:
    od = tmp_path / "out"
    _seed_required(od)
    manifest = build_runtime_manifest(output_dir=od)
    write_runtime_manifest(default_runtime_manifest_path(od), manifest)
    (od / "runtime" / "health_snapshot.json").write_text('{"tampered":true}', encoding="utf-8")

    result = verify_runtime_manifest(output_dir=od)
    assert result["verification_status"] == "FAIL"
    assert result["checksum_mismatches"]


def test_missing_optional_warning(tmp_path: Path) -> None:
    od = tmp_path / "out"
    _seed_required(od)
    manifest = build_runtime_manifest(output_dir=od)
    write_runtime_manifest(default_runtime_manifest_path(od), manifest)

    result = verify_runtime_manifest(output_dir=od)
    assert result["verification_status"] == "WARNING"
    assert "qualification.json" in result["missing_optional"]


def test_strict_exit_codes() -> None:
    assert strict_verify_exit_code({"verification_status": "OK"}, strict=False) == 0
    assert strict_verify_exit_code({"verification_status": "OK"}, strict=True) == 0
    assert strict_verify_exit_code({"verification_status": "WARNING"}, strict=False) == 0
    assert strict_verify_exit_code({"verification_status": "WARNING"}, strict=True) == 1
    assert strict_verify_exit_code({"verification_status": "FAIL"}, strict=True) == 1


def test_verify_required_and_checksums_helpers(tmp_path: Path) -> None:
    od = tmp_path / "out"
    _seed_required(od)
    manifest = build_runtime_manifest(output_dir=od)
    missing, warns = verify_required_artifacts(od, manifest)
    assert missing == []
    assert any("missing_optional" in w for w in warns)

    mismatches, _ = verify_artifact_checksums(od, manifest)
    assert mismatches == []


def test_cli_verify_runtime_strict_exit(tmp_path: Path) -> None:
    od = tmp_path / "out"
    (od / "runtime").mkdir(parents=True)
    manifest = build_runtime_manifest(output_dir=od)
    write_runtime_manifest(default_runtime_manifest_path(od), manifest)

    proc = subprocess.run(
        [sys.executable, "-m", "newsroom.cli", "verify-runtime", "--path", str(od), "--strict"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1


def test_reproducible_zip_ordering(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from dataclasses import replace

    rd = tmp_path / "runtime_state"
    rd.mkdir()
    (rd / "soak_report.json").write_text('{"ok":true}', encoding="utf-8")

    class _Settings:
        runtime_state_dir = str(rd)
        redis_enabled = False

    settings = _Settings()
    z1 = tmp_path / "a.zip"
    z2 = tmp_path / "b.zip"
    write_runtime_bundle(rd, z1, settings, include_html=False, fail_on_missing=False)
    write_runtime_bundle(rd, z2, settings, include_html=False, fail_on_missing=False)

    with zipfile.ZipFile(z1) as za, zipfile.ZipFile(z2) as zb:
        names_a = za.namelist()
        names_b = zb.namelist()
    assert names_a == names_b
    assert names_a == sorted(names_a)
    for zpath in (z1, z2):
        with zipfile.ZipFile(zpath) as zf:
            for info in zf.infolist():
                assert info.date_time == ZIP_FIXED_DTIME
