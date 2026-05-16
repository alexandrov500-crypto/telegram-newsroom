from __future__ import annotations

from pathlib import Path

from editorial.intelligence_store import operational_timeline_path, save_json, suppression_state_path
from utils.runtime_integrity import (
    summarize_runtime_state_dir,
    validate_operational_timeline,
    validate_suppression_state,
)


def test_validate_timeline_empty_dir(tmp_path: Path) -> None:
    assert validate_operational_timeline(str(tmp_path)) == []


def test_validate_timeline_bad_version(tmp_path: Path) -> None:
    p = operational_timeline_path(str(tmp_path))
    save_json(p, {"version": 99, "events": []})
    issues = validate_operational_timeline(str(tmp_path))
    assert any("version" in x.lower() for x in issues)


def test_validate_timeline_invalid_json_file(tmp_path: Path) -> None:
    p = operational_timeline_path(str(tmp_path))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{broken", encoding="utf-8")
    issues = validate_operational_timeline(str(tmp_path))
    assert any("invalid_json" in x for x in issues)


def test_validate_suppression_bad_entries(tmp_path: Path) -> None:
    p = suppression_state_path(str(tmp_path))
    save_json(p, {"version": 1, "entries": [], "duplicate_burst": "bad"})
    issues = validate_suppression_state(str(tmp_path))
    assert issues


def test_summarize_runtime_state(tmp_path: Path) -> None:
    (tmp_path / "operational_timeline.json").write_text("{}", encoding="utf-8")
    s = summarize_runtime_state_dir(str(tmp_path))
    assert s.get("exists") is True
    assert "operational_timeline.json" in s.get("files", {})
