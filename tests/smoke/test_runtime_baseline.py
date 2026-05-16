"""Smoke tests for runtime baseline and drift comparison."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from observability.runtime_baseline import (
    BASELINE_KEY_ORDER,
    DRIFT_KEY_ORDER,
    RUNTIME_DURATION_WARNING_THRESHOLD_SEC,
    build_drift_report,
    build_runtime_baseline,
    compare_runtime_against_baseline,
    create_runtime_baseline,
    default_runtime_baseline_path,
    load_runtime_baseline,
    strict_drift_exit_code,
    write_runtime_baseline,
)

REPO = Path(__file__).resolve().parents[2]


def _seed(od: Path, *, qual: str = "OK", incident: str = "NONE", duration: float = 83.412) -> None:
    rt = od / "runtime"
    rt.mkdir(parents=True, exist_ok=True)
    (rt / "health_snapshot.json").write_text(
        json.dumps({"schema_version": 1, "runtime_duration_sec": duration, "pipeline_status": "OK"}),
        encoding="utf-8",
    )
    (rt / "runtime_report.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "incident_level": incident,
                "qualification_status": qual,
            },
        ),
        encoding="utf-8",
    )
    (rt / "runtime_manifest.json").write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
    (rt / "recovery_report.json").write_text(
        json.dumps({"schema_version": 1, "recovery_status": "OK", "verification_status": "OK"}),
        encoding="utf-8",
    )
    (rt / "compatibility_report.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "compatibility_status": "OK",
                "artifact_versions": {
                    "health_snapshot.json": 1,
                    "runtime_report.json": 1,
                    "runtime_manifest.json": 1,
                    "recovery_report.json": 1,
                },
            },
        ),
        encoding="utf-8",
    )
    (od / "qualification.json").write_text(
        json.dumps({"qualification_status": qual}),
        encoding="utf-8",
    )


def test_baseline_schema(tmp_path: Path) -> None:
    od = tmp_path / "out"
    _seed(od)
    baseline = build_runtime_baseline(od)
    assert list(baseline.keys()) == list(BASELINE_KEY_ORDER)
    assert baseline["schema_version"] == 1
    assert baseline["qualification_status"] == "OK"


def test_idempotent_baseline_fields(tmp_path: Path) -> None:
    od = tmp_path / "out"
    _seed(od)
    a = build_runtime_baseline(od)
    b = build_runtime_baseline(od)
    a.pop("generated_at", None)
    b.pop("generated_at", None)
    assert a == b


def test_drift_ok_when_matching(tmp_path: Path) -> None:
    od = tmp_path / "out"
    _seed(od)
    baseline = build_runtime_baseline(od)
    write_runtime_baseline(default_runtime_baseline_path(od), baseline)
    drift = build_drift_report(od)
    assert drift["drift_status"] == "OK"
    assert drift["baseline_present"] is True
    assert list(drift.keys()) == list(DRIFT_KEY_ORDER)


def test_qualification_downgrade_warning(tmp_path: Path) -> None:
    od = tmp_path / "out"
    _seed(od, qual="OK")
    baseline = build_runtime_baseline(od)
    write_runtime_baseline(default_runtime_baseline_path(od), baseline)
    _seed(od, qual="WARNING")
    drift = build_drift_report(od)
    assert drift["drift_status"] == "WARNING"
    assert drift["qualification_changed"] is True
    assert "qualification_status_downgrade" in drift["drift_warnings"]


def test_runtime_duration_threshold_warning(tmp_path: Path) -> None:
    od = tmp_path / "out"
    _seed(od, duration=80.0)
    baseline = build_runtime_baseline(od)
    write_runtime_baseline(default_runtime_baseline_path(od), baseline)
    _seed(od, duration=80.0 + RUNTIME_DURATION_WARNING_THRESHOLD_SEC + 1.0)
    drift = build_drift_report(od)
    assert drift["drift_status"] == "WARNING"
    assert "runtime_duration_delta_exceeds_threshold" in drift["drift_warnings"]


def test_artifact_version_drift(tmp_path: Path) -> None:
    od = tmp_path / "out"
    _seed(od)
    baseline = build_runtime_baseline(od)
    write_runtime_baseline(default_runtime_baseline_path(od), baseline)
    compat = json.loads((od / "runtime" / "compatibility_report.json").read_text(encoding="utf-8"))
    compat["artifact_versions"]["health_snapshot.json"] = 2
    (od / "runtime" / "compatibility_report.json").write_text(
        json.dumps(compat, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    hs = json.loads((od / "runtime" / "health_snapshot.json").read_text(encoding="utf-8"))
    hs["schema_version"] = 2
    (od / "runtime" / "health_snapshot.json").write_text(
        json.dumps(hs, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    cmp = compare_runtime_against_baseline(od)
    drift = build_drift_report(od, cmp)
    assert drift["artifact_version_drift"]
    assert drift["drift_status"] == "WARNING"


def test_missing_baseline_warning(tmp_path: Path) -> None:
    od = tmp_path / "out"
    _seed(od)
    drift = build_drift_report(od)
    assert drift["baseline_present"] is False
    assert drift["drift_status"] == "WARNING"


def test_unreadable_baseline_fail(tmp_path: Path) -> None:
    od = tmp_path / "out"
    _seed(od)
    p = default_runtime_baseline_path(od)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("not json", encoding="utf-8")
    drift = build_drift_report(od)
    assert drift["drift_status"] == "FAIL"


def test_strict_exit_codes() -> None:
    assert strict_drift_exit_code({"drift_status": "OK"}, strict=True) == 0
    assert strict_drift_exit_code({"drift_status": "WARNING"}, strict=True) == 1
    assert strict_drift_exit_code({"drift_status": "FAIL"}, strict=False) == 1


def test_cli_compare_strict(tmp_path: Path) -> None:
    od = tmp_path / "out"
    _seed(od, qual="OK")
    create_runtime_baseline(od)
    _seed(od, qual="FAIL", incident="ERROR")
    proc = subprocess.run(
        [sys.executable, "-m", "newsroom.cli", "compare-baseline", "--path", str(od), "--strict"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1


def test_load_baseline_roundtrip(tmp_path: Path) -> None:
    od = tmp_path / "out"
    _seed(od)
    create_runtime_baseline(od)
    loaded = load_runtime_baseline(default_runtime_baseline_path(od))
    assert loaded is not None
    assert loaded["qualification_status"] == "OK"
