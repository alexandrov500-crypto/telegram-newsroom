"""Smoke tests for bounded qualification history and audit snapshots."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from observability.runtime_history import (
    AUDIT_KEY_ORDER,
    HISTORY_KEY_ORDER,
    HISTORY_LIMIT,
    append_qualification_history,
    build_audit_snapshot,
    collect_history_entry_from_output_dir,
    default_qualification_history_path,
    load_qualification_history,
    rotate_qualification_history,
    strict_audit_exit_code,
    update_runtime_history,
    write_audit_snapshot,
    write_qualification_history,
)

REPO = Path(__file__).resolve().parents[2]


def _entry(ts: str, qual: str = "OK") -> dict:
    return {
        "timestamp": ts,
        "qualification_status": qual,
        "verification_status": "OK",
        "recovery_status": "OK",
        "compatibility_status": "OK",
        "incident_level": "NONE",
        "runtime_duration_sec": 1.0,
        "bundle_status": "OK",
    }


def test_history_schema_and_bounded_trim(tmp_path: Path) -> None:
    od = tmp_path / "out"
    od.mkdir()
    hist_path = default_qualification_history_path(od)
    for i in range(25):
        append_qualification_history(od, _entry(f"2026-05-15T12:{i:02d}:00Z", "OK"))

    hist = load_qualification_history(hist_path)
    assert list(hist.keys()) == list(HISTORY_KEY_ORDER)
    assert hist["schema_version"] == 1
    assert hist["history_limit"] == HISTORY_LIMIT
    assert len(hist["entries"]) == HISTORY_LIMIT
    timestamps = [e["timestamp"] for e in hist["entries"]]
    assert timestamps == sorted(timestamps, reverse=True)


def test_latest_first_ordering(tmp_path: Path) -> None:
    od = tmp_path / "out"
    od.mkdir()
    append_qualification_history(od, _entry("2026-05-15T12:01:00Z"))
    append_qualification_history(od, _entry("2026-05-15T12:02:00Z"))
    hist = load_qualification_history(default_qualification_history_path(od))
    assert hist["entries"][0]["timestamp"] == "2026-05-15T12:02:00Z"


def test_rotation_idempotency(tmp_path: Path) -> None:
    doc = {
        "schema_version": 1,
        "history_limit": 3,
        "entries": [_entry("2026-05-15T12:03:00Z"), _entry("2026-05-15T12:02:00Z")],
    }
    a = rotate_qualification_history(doc)
    b = rotate_qualification_history(a)
    assert a == b


def test_deterministic_history_json(tmp_path: Path) -> None:
    od = tmp_path / "out"
    od.mkdir()
    hist = {
        "schema_version": 1,
        "history_limit": 20,
        "entries": [_entry("2026-05-15T12:50:00Z")],
    }
    p = default_qualification_history_path(od)
    write_qualification_history(p, hist)
    loaded = json.loads(p.read_text(encoding="utf-8"))
    assert loaded["entries"][0]["qualification_status"] == "OK"


def test_audit_snapshot_schema_and_aggregation(tmp_path: Path) -> None:
    od = tmp_path / "out"
    od.mkdir()
    entries = [
        _entry("2026-05-15T12:50:00Z", "OK"),
        _entry("2026-05-15T12:49:00Z", "WARNING"),
        _entry("2026-05-15T12:48:00Z", "FAIL"),
    ]
    hist = {"schema_version": 1, "history_limit": 20, "entries": entries}
    write_qualification_history(default_qualification_history_path(od), hist)
    audit = build_audit_snapshot(od, history=load_qualification_history(default_qualification_history_path(od)))
    assert list(audit.keys()) == list(AUDIT_KEY_ORDER)
    assert audit["status_summary"]["OK"] == 1
    assert audit["status_summary"]["WARNING"] == 1
    assert audit["status_summary"]["FAIL"] == 1
    assert audit["latest_qualification_status"] == "OK"
    assert audit["recent_failures"]


def test_append_semantics(tmp_path: Path) -> None:
    od = tmp_path / "out"
    od.mkdir()
    append_qualification_history(od, _entry("2026-05-15T12:50:00Z", "OK"))
    append_qualification_history(od, _entry("2026-05-15T12:51:00Z", "WARNING"))
    hist = load_qualification_history(default_qualification_history_path(od))
    assert len(hist["entries"]) == 2
    assert hist["entries"][0]["qualification_status"] == "WARNING"


def test_strict_exit_codes() -> None:
    assert strict_audit_exit_code({"audit_status": "OK", "latest_qualification_status": "OK"}, strict=True) == 0
    assert strict_audit_exit_code({"audit_status": "WARNING", "latest_qualification_status": "OK"}, strict=True) == 1
    assert strict_audit_exit_code({"audit_status": "OK", "latest_qualification_status": "FAIL"}, strict=False) == 1


def test_update_runtime_history_from_artifacts(tmp_path: Path) -> None:
    od = tmp_path / "out"
    rt = od / "runtime"
    rt.mkdir(parents=True)
    (rt / "health_snapshot.json").write_text(
        json.dumps({"schema_version": 1, "runtime_duration_sec": 83.412, "pipeline_status": "OK"}),
        encoding="utf-8",
    )
    (rt / "runtime_report.json").write_text(
        json.dumps({"schema_version": 1, "incident_level": "NONE", "qualification_status": "OK"}),
        encoding="utf-8",
    )
    (od / "qualification.json").write_text(
        json.dumps({"qualification_status": "OK"}),
        encoding="utf-8",
    )
    entry = collect_history_entry_from_output_dir(od)
    assert entry["runtime_duration_sec"] == 83.412
    hist_path, audit_path = update_runtime_history(od, entry=entry)
    assert hist_path.is_file()
    assert audit_path.is_file()


def test_cli_audit_runtime_strict(tmp_path: Path) -> None:
    od = tmp_path / "out"
    od.mkdir()
    rt = od / "runtime"
    rt.mkdir(parents=True)
    audit = {
        "schema_version": 1,
        "generated_at": "2026-05-15T12:55:00Z",
        "audit_status": "FAIL",
        "history_entries": 1,
        "latest_qualification_status": "FAIL",
        "latest_incident_level": "ERROR",
        "status_summary": {"OK": 0, "WARNING": 0, "FAIL": 1},
        "recent_failures": ["fail"],
        "recent_warnings": [],
    }
    (rt / "audit_snapshot.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    (rt / "qualification_history.json").write_text(
        json.dumps({"schema_version": 1, "history_limit": 20, "entries": []}),
        encoding="utf-8",
    )

    proc = subprocess.run(
        [sys.executable, "-m", "newsroom.cli", "audit-runtime", "--path", str(od), "--strict"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
