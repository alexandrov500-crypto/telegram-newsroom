"""Smoke tests for deterministic runtime report (no network)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from observability.runtime_report import (
    REPORT_KEY_ORDER,
    build_incident_summary,
    build_runtime_report,
    default_runtime_report_path,
    load_runtime_report,
    strict_report_exit_code,
    write_runtime_report,
)

REPO = Path(__file__).resolve().parents[2]


def _ops(*, status: str = "OK", failed: list[str] | None = None) -> dict:
    steps = [{"name": "preflight", "status": "OK"}, {"name": "benchmark", "status": "OK"}]
    if failed:
        for n in failed:
            steps.append({"name": n, "status": "FAIL"})
    return {"command": "nightly-check", "status": status, "steps": steps}


def _health(*, failed: list[str] | None = None, qual: str | None = "OK") -> dict:
    return {
        "pipeline_status": "OK",
        "runtime_duration_sec": 83.412,
        "failed_steps": failed or [],
        "qualification_status": qual,
        "collected_articles": 10,
        "generated_drafts": 2,
        "published_posts": 1,
    }


def test_report_schema_and_key_order(tmp_path: Path) -> None:
    od = tmp_path / "out"
    od.mkdir()
    (od / "runtime").mkdir(parents=True, exist_ok=True)
    (od / "qualification.json").write_text(
        json.dumps({"qualification_status": "OK"}),
        encoding="utf-8",
    )
    (od / "runtime_bundle.zip").write_bytes(b"x" * 1024)
    hp = od / "runtime" / "health_snapshot.json"
    hp.write_text("{}", encoding="utf-8")

    rpt = build_runtime_report(
        ops_report=_ops(),
        output_dir=od,
        health_snapshot=_health(),
        health_snapshot_path=hp,
    )
    assert list(rpt.keys()) == list(REPORT_KEY_ORDER)
    assert rpt["artifact_inventory"]["runtime_bundle"] is True
    assert rpt["runtime_bundle"]["exists"] is True
    assert rpt["runtime_bundle"]["size_mb"] is not None


def test_incident_error_on_failed_steps() -> None:
    level, summ, _w = build_incident_summary(
        health_snapshot=_health(failed=["bundle"]),
        qualification_status="OK",
        artifact_inventory={"health_snapshot": True, "runtime_bundle": True, "qualification_report": True},
        report_warnings=[],
    )
    assert level == "ERROR"
    assert any("failed_steps" in s for s in summ)


def test_incident_warning_on_missing_artifact() -> None:
    level, _summ, warns = build_incident_summary(
        health_snapshot=_health(),
        qualification_status="OK",
        artifact_inventory={"health_snapshot": True, "runtime_bundle": False, "qualification_report": False},
        report_warnings=["missing:runtime_bundle.zip"],
    )
    assert level == "WARNING"
    assert any("missing_artifact" in w for w in warns)


def test_missing_bundle_does_not_raise(tmp_path: Path) -> None:
    od = tmp_path / "empty"
    od.mkdir()
    rpt = build_runtime_report(
        ops_report=_ops(),
        output_dir=od,
        health_snapshot=_health(),
    )
    assert rpt["runtime_bundle"]["exists"] is False
    assert any("missing" in w for w in rpt["warnings"])


def test_write_idempotent_keys(tmp_path: Path) -> None:
    od = tmp_path / "idempotent"
    od.mkdir()
    path = default_runtime_report_path(od)
    base = build_runtime_report(ops_report=_ops(), output_dir=od, health_snapshot=_health())
    # freeze generated_at for comparison
    base["generated_at"] = "2026-05-15T00:00:00Z"
    write_runtime_report(path, base)
    again = build_runtime_report(ops_report=_ops(), output_dir=od, health_snapshot=_health())
    again["generated_at"] = "2026-05-15T00:00:00Z"
    assert list(base.keys()) == list(again.keys())
    assert base["incident_level"] == again["incident_level"]
    loaded = load_runtime_report(path)
    assert loaded is not None
    assert loaded["incident_level"] == base["incident_level"]


def test_strict_exit_code() -> None:
    assert strict_report_exit_code({"incident_level": "NONE"}) == 0
    assert strict_report_exit_code({"incident_level": "WARNING"}) == 1
    assert strict_report_exit_code({"incident_level": "ERROR"}) == 1


def test_cli_report_and_strict(tmp_path: Path) -> None:
    od = tmp_path / "cli"
    od.mkdir()
    rpt = build_runtime_report(
        ops_report=_ops(failed=["bundle"]),
        output_dir=od,
        health_snapshot=_health(failed=["bundle"], qual="FAIL"),
    )
    write_runtime_report(default_runtime_report_path(od), rpt)

    proc = subprocess.run(
        [sys.executable, "-m", "newsroom.cli", "health", "--path", str(od), "--report"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(REPO)},
    )
    assert proc.returncode == 0, proc.stderr
    assert "Incident level: ERROR" in proc.stdout

    proc_strict = subprocess.run(
        [sys.executable, "-m", "newsroom.cli", "health", "--path", str(od), "--report", "--strict"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(REPO)},
    )
    assert proc_strict.returncode == 1
