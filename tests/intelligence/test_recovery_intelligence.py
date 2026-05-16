"""Recovery intelligence heuristics."""

from __future__ import annotations

from pathlib import Path

from utils.recovery_intelligence import (
    build_recovery_assessment,
    detect_unsafe_recovery_patterns,
    estimate_restore_duration_sec,
)


def test_restore_estimate_scales() -> None:
    small = estimate_restore_duration_sec(output_dir_bytes=1_000_000)
    large = estimate_restore_duration_sec(output_dir_bytes=200_000_000)
    assert large > small


def test_unsafe_restore_patterns() -> None:
    p = detect_unsafe_recovery_patterns(
        live_db=True,
        workers_running=True,
        restore_over_active_db=True,
    )
    assert len(p) >= 2


def test_recovery_assessment_empty_dir(tmp_path: Path) -> None:
    r = build_recovery_assessment(tmp_path / "out")
    assert r["read_only"] is True
    assert "restore_duration_estimate_sec" in r
