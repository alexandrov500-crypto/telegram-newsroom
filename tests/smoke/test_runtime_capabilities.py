"""Smoke tests for runtime capability profiles and deployment semantics."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from observability.runtime_capabilities import (
    CANONICAL_DEPLOYMENT_PROFILE,
    CANONICAL_RUNTIME_MODEL,
    PROFILE_KEY_ORDER,
    REPORT_KEY_ORDER,
    build_capability_report,
    build_runtime_capability_profile,
    load_runtime_capability_profile,
    strict_capability_exit_code,
    update_runtime_capabilities,
    validate_runtime_capabilities,
    write_runtime_capability_profile,
)

REPO = Path(__file__).resolve().parents[2]


def test_capability_profile_schema() -> None:
    profile = build_runtime_capability_profile(None)
    assert list(profile.keys()) == list(PROFILE_KEY_ORDER)
    assert profile["schema_version"] == 1
    assert profile["runtime_model"] == CANONICAL_RUNTIME_MODEL
    assert profile["deployment_profile"] == CANONICAL_DEPLOYMENT_PROFILE
    assert profile["runtime_characteristics"]["bounded_state"] is True


def test_idempotent_capability_generation(tmp_path: Path) -> None:
    od = tmp_path / "out"
    od.mkdir()
    a = build_runtime_capability_profile(od)
    b = build_runtime_capability_profile(od)
    a.pop("generated_at", None)
    b.pop("generated_at", None)
    assert a == b


def test_supported_deployment_validation_ok(tmp_path: Path) -> None:
    od = tmp_path / "out"
    od.mkdir()
    profile = build_runtime_capability_profile(od)
    validation = validate_runtime_capabilities(profile)
    report = build_capability_report(od, profile=profile)
    assert validation["capability_validation_status"] == "OK"
    assert list(report.keys()) == list(REPORT_KEY_ORDER)
    assert report["runtime_model_supported"] is True
    assert report["deployment_profile_supported"] is True


def test_unsupported_runtime_model_fail() -> None:
    profile = build_runtime_capability_profile(None, runtime_model="multi-node-runtime")
    validation = validate_runtime_capabilities(profile)
    assert validation["capability_validation_status"] == "FAIL"
    assert any("unsupported_runtime_model" in f for f in validation["capability_failures"])


def test_invalid_deployment_profile_fail() -> None:
    profile = build_runtime_capability_profile(None, deployment_profile="kubernetes-prod")
    validation = validate_runtime_capabilities(profile)
    assert validation["capability_validation_status"] == "FAIL"


def test_missing_required_capability_fail() -> None:
    profile = build_runtime_capability_profile(None)
    profile = dict(profile)
    chars = dict(profile["runtime_characteristics"])
    chars["bounded_state"] = False
    profile["runtime_characteristics"] = chars
    validation = validate_runtime_capabilities(profile)
    assert validation["capability_validation_status"] == "FAIL"
    assert any("missing_required_capability" in f for f in validation["capability_failures"])


def test_unknown_execution_mode_warning() -> None:
    profile = build_runtime_capability_profile(None)
    validation = validate_runtime_capabilities(
        profile,
        execution_mode_hint="kubernetes-cluster",
    )
    assert validation["capability_validation_status"] == "WARNING"
    assert any("unsupported_execution_mode_hint" in w for w in validation["capability_warnings"])


def test_constraint_validation(tmp_path: Path) -> None:
    profile = build_runtime_capability_profile(tmp_path / "out")
    profile = dict(profile)
    profile["operational_constraints"] = ["single_writer_runtime"]
    validation = validate_runtime_capabilities(profile)
    assert validation["capability_validation_status"] == "WARNING"
    assert validation["constraint_violations"]


def test_update_runtime_capabilities_writes_files(tmp_path: Path) -> None:
    od = tmp_path / "out"
    od.mkdir()
    prof_path, rep_path = update_runtime_capabilities(od)
    assert prof_path.is_file()
    assert rep_path.is_file()
    loaded = load_runtime_capability_profile(prof_path)
    assert loaded is not None
    assert loaded["capability_status"] in ("OK", "WARNING", "FAIL")


def test_strict_exit_codes() -> None:
    assert strict_capability_exit_code({"capability_validation_status": "OK"}, strict=True) == 0
    assert strict_capability_exit_code({"capability_validation_status": "WARNING"}, strict=True) == 1
    assert strict_capability_exit_code({"capability_validation_status": "FAIL"}, strict=False) == 1


def test_cli_inspect_capabilities_strict(tmp_path: Path) -> None:
    od = tmp_path / "out"
    rt = od / "runtime"
    rt.mkdir(parents=True)
    profile = build_runtime_capability_profile(od, runtime_model="kubernetes-cluster")
    write_runtime_capability_profile(rt / "runtime_capabilities.json", profile)
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "newsroom.cli",
            "inspect-capabilities",
            "--path",
            str(od),
            "--strict",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
