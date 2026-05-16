from __future__ import annotations

from pathlib import Path

from tests.helpers.failure_injection import corrupt_suppression_state_partial, malformed_json_operational_timeline, restore_text_file
from utils.runtime_integrity import validate_operational_timeline, validate_suppression_state


def test_malformed_timeline_detected(tmp_path: Path) -> None:
    rd = str(tmp_path)
    with malformed_json_operational_timeline(rd):
        issues = validate_operational_timeline(rd)
        assert any("invalid_json" in x for x in issues)


def test_corrupt_suppression_duplicate_burst_detected(tmp_path: Path) -> None:
    rd = str(tmp_path)
    path, prev = corrupt_suppression_state_partial(rd)
    try:
        issues = validate_suppression_state(rd)
        assert any("duplicate_burst" in x for x in issues)
    finally:
        restore_text_file(path, prev)
