"""Smoke tests for runtime schema compatibility (inspection-only, no network)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from observability.health_snapshot import build_health_snapshot, write_health_snapshot
from observability.runtime_manifest import build_runtime_manifest, write_runtime_manifest
from observability.runtime_recovery import validate_runtime_recovery, write_recovery_report
from observability.runtime_report import build_runtime_report, write_runtime_report
from observability.runtime_schema import (
    COMPATIBILITY_KEY_ORDER,
    CURRENT_RUNTIME_SCHEMA_VERSION,
    FUTURE_COMPATIBLE_VERSIONS,
    build_compatibility_report,
    check_runtime_compatibility,
    default_compatibility_report_path,
    get_supported_schema_versions,
    strict_compatibility_exit_code,
    validate_schema_version,
    write_compatibility_report,
)

REPO = Path(__file__).resolve().parents[2]


def _ops() -> dict:
    return {
        "command": "nightly-check",
        "status": "OK",
        "started_at": "2026-05-15T12:00:00Z",
        "completed_at": "2026-05-15T12:01:00Z",
        "steps": [{"name": "preflight", "status": "OK"}],
    }


def _seed_v1(od: Path) -> None:
    od.mkdir(parents=True, exist_ok=True)
    snap = build_health_snapshot(ops_report=_ops(), output_dir=od)
    write_health_snapshot(od / "runtime" / "health_snapshot.json", snap)
    rpt = build_runtime_report(ops_report=_ops(), output_dir=od, health_snapshot=snap)
    write_runtime_report(od / "runtime" / "runtime_report.json", rpt)
    man = build_runtime_manifest(output_dir=od, ops_report=_ops())
    write_runtime_manifest(od / "runtime" / "runtime_manifest.json", man)
    rec = validate_runtime_recovery(od)
    write_recovery_report(od / "runtime" / "recovery_report.json", rec)


def test_schema_version_on_all_artifacts(tmp_path: Path) -> None:
    od = tmp_path / "out"
    _seed_v1(od)
    for rel in (
        "runtime/health_snapshot.json",
        "runtime/runtime_report.json",
        "runtime/runtime_manifest.json",
        "runtime/recovery_report.json",
    ):
        doc = json.loads((od / rel).read_text(encoding="utf-8"))
        assert doc["schema_version"] == CURRENT_RUNTIME_SCHEMA_VERSION


def test_supported_versions_list() -> None:
    assert get_supported_schema_versions() == [CURRENT_RUNTIME_SCHEMA_VERSION]


def test_unsupported_version_fails() -> None:
    st, msgs = validate_schema_version(99, artifact_name="health_snapshot.json")
    assert st == "FAIL"
    assert any("unsupported" in m for m in msgs)


def test_malformed_version_fails() -> None:
    st, _ = validate_schema_version("v1", artifact_name="x.json")
    assert st == "FAIL"
    st2, _ = validate_schema_version(-1, artifact_name="x.json")
    assert st2 == "FAIL"
    st3, _ = validate_schema_version(True, artifact_name="x.json")
    assert st3 == "FAIL"


def test_missing_schema_version_fails() -> None:
    st, msgs = validate_schema_version(None, artifact_name="runtime_report.json", required=True)
    assert st == "FAIL"
    assert "missing_schema_version" in msgs[0]


def test_future_compatible_warning() -> None:
    if not FUTURE_COMPATIBLE_VERSIONS:
        return
    future = min(FUTURE_COMPATIBLE_VERSIONS)
    st, msgs = validate_schema_version(future, artifact_name="health_snapshot.json")
    assert st == "WARNING"
    assert any("future_schema_version" in m for m in msgs)


def test_compatibility_ok_report(tmp_path: Path) -> None:
    od = tmp_path / "out"
    _seed_v1(od)
    report = check_runtime_compatibility(od)
    assert report["compatibility_status"] == "OK"
    assert report["runtime_schema_version"] == CURRENT_RUNTIME_SCHEMA_VERSION
    assert report["artifact_versions"]["health_snapshot.json"] == 1


def test_compatibility_report_deterministic_write(tmp_path: Path) -> None:
    od = tmp_path / "out"
    _seed_v1(od)
    r1 = build_compatibility_report(od)
    r2 = build_compatibility_report(od)
    r1["generated_at"] = "2026-05-15T12:40:00Z"
    r2["generated_at"] = "2026-05-15T12:40:00Z"
    p = default_compatibility_report_path(od)
    write_compatibility_report(p, r1)
    write_compatibility_report(p, r2)
    assert "schema_version" in json.loads(p.read_text(encoding="utf-8"))


def test_compatibility_idempotency(tmp_path: Path) -> None:
    od = tmp_path / "out"
    _seed_v1(od)
    a = build_compatibility_report(od)
    b = build_compatibility_report(od)
    a.pop("generated_at", None)
    b.pop("generated_at", None)
    assert a == b


def test_strict_exit_codes() -> None:
    assert strict_compatibility_exit_code({"compatibility_status": "OK"}, strict=True) == 0
    assert strict_compatibility_exit_code({"compatibility_status": "WARNING"}, strict=True) == 1
    assert strict_compatibility_exit_code({"compatibility_status": "FAIL"}, strict=False) == 1


def test_cli_check_compatibility_strict(tmp_path: Path) -> None:
    od = tmp_path / "out"
    (od / "runtime").mkdir(parents=True)
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "newsroom.cli",
            "check-compatibility",
            "--path",
            str(od),
            "--strict",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1


def test_future_version_file_warning(tmp_path: Path) -> None:
    if not FUTURE_COMPATIBLE_VERSIONS:
        return
    od = tmp_path / "out"
    _seed_v1(od)
    future = min(FUTURE_COMPATIBLE_VERSIONS)
    hp = od / "runtime" / "health_snapshot.json"
    doc = json.loads(hp.read_text(encoding="utf-8"))
    doc["schema_version"] = future
    hp.write_text(json.dumps(doc, indent=2, sort_keys=True), encoding="utf-8")
    report = check_runtime_compatibility(od)
    assert report["compatibility_status"] == "WARNING"
    assert report["artifact_versions"]["health_snapshot.json"] == future
