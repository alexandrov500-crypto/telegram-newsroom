from __future__ import annotations

from pathlib import Path

from bot.ops_consolidation.contracts import subsystem_contracts
from bot.ops_consolidation.metrics import compute_complexity_metrics
from bot.ops_consolidation.report import build_consolidation_report
from bot.ops_consolidation.service import maybe_dedupe_operator_context
from bot.ops_consolidation.signals import analyze_signal_overlap, dedupe_context_signals
from bot.ops_consolidation.stability import (
    architecture_stability_phase_enabled,
    check_subsystem_addition,
)
from bot.storage.db import init_database


def test_subsystem_contracts() -> None:
    contracts = subsystem_contracts()
    assert "runtime" in contracts
    assert "resilience" in contracts
    assert contracts["trust_calibration"]["failure_behavior"] == "fail-open"


def test_signal_overlap_analysis() -> None:
    analysis = analyze_signal_overlap()
    assert len(analysis["overlap_groups"]) >= 3


def test_dedupe_context() -> None:
    ctx = {"pulse": {"event_loop_lag_max": 0.1, "anomalies": []}, "priority_drift": {}}
    out = dedupe_context_signals(ctx)
    assert out.get("_signals_deduped") is True


def test_complexity_metrics(tmp_path: Path) -> None:
    db = init_database(tmp_path / "consolidation.db")
    m = compute_complexity_metrics(db)
    assert "complexity_score" in m
    assert m["background_loop_count"] >= 1


def test_build_report(tmp_path: Path) -> None:
    db = init_database(tmp_path / "consolidation2.db")
    report = build_consolidation_report(db, persist=True)
    assert "maintenance_burden" in report
    assert "consolidation_actions" in report


def test_stability_check_allowed() -> None:
    result = check_subsystem_addition("test_subsystem", experimental=True)
    assert result["allowed"] is True
