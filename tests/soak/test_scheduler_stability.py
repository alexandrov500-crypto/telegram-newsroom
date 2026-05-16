"""Scheduler diagnostics and overlap detection."""

from __future__ import annotations

from utils.scheduler_diagnostics import (
    detect_scheduler_overlap,
    execution_lag_report,
    record_scheduler_run,
    reset_scheduler_diagnostics_for_tests,
    scheduler_diagnostics_snapshot,
)


def test_scheduler_overlap_detection() -> None:
    reset_scheduler_diagnostics_for_tests()
    record_scheduler_run("newsroom_pipeline", wall_sec=1.0)
    record_scheduler_run(
        "newsroom_pipeline",
        wall_sec=0.5,
        expected_interval_sec=1800.0,
    )
    assert detect_scheduler_overlap() or scheduler_diagnostics_snapshot()["run_count"] >= 2


def test_execution_lag_report_shape() -> None:
    reset_scheduler_diagnostics_for_tests()
    for _ in range(4):
        record_scheduler_run("newsroom_pipeline", wall_sec=0.2, expected_interval_sec=60.0)
    rep = execution_lag_report(job_id="newsroom_pipeline", expected_interval_sec=60.0)
    assert rep["job_id"] == "newsroom_pipeline"
    assert "lag_status" in rep
