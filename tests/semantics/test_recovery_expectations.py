"""Recovery semantics helpers."""

from __future__ import annotations

from pathlib import Path

from utils.recovery_intelligence import build_recovery_assessment, detect_unsafe_recovery_patterns


def test_non_guarantee_unsafe_live_restore() -> None:
    patterns = detect_unsafe_recovery_patterns(
        live_db=True,
        workers_running=True,
        restore_over_active_db=True,
    )
    assert len(patterns) >= 2


def test_partial_output_dir_warning(tmp_path: Path) -> None:
    od = tmp_path / "out"
    rt = od / "runtime"
    rt.mkdir(parents=True)
    (rt / "health_snapshot.json").write_text("{}", encoding="utf-8")
    from tools.semantics_guardrails import check_retention_invariants

    findings = check_retention_invariants(od)
    assert any(f["code"] == "partial_recovery_state" for f in findings)


def test_complete_empty_assessment(tmp_path: Path) -> None:
    r = build_recovery_assessment(tmp_path / "empty")
    assert r["read_only"] is True
