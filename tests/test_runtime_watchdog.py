from __future__ import annotations

from tests.conftest import minimal_test_settings
from workers.watchdog import evaluate_runtime_watchdogs


def test_watchdog_retry_storm_warning() -> None:
    s = minimal_test_settings(runtime_retry_storm_count=3, runtime_retry_storm_window_sec=60.0)
    warns = evaluate_runtime_watchdogs(
        s,
        worker_role="ai",
        job_kind="ai",
        counters={"retry_burst_window": 5, "active_jobs": 0},
        queue_pressure={"pending_depth": 0, "processing_depth": 0},
    )
    codes = [w["code"] for w in warns]
    assert "retry_storm" in codes


def test_watchdog_long_job_warning() -> None:
    s = minimal_test_settings(runtime_active_job_warn_sec=10.0)
    warns = evaluate_runtime_watchdogs(
        s,
        worker_role="ingest",
        job_kind="ingest",
        counters={"retry_burst_window": 0, "active_jobs": 1, "oldest_active_job_age_sec": 20.0},
        queue_pressure={"pending_depth": 1, "processing_depth": 0},
    )
    assert any(w["code"] == "long_running_job" for w in warns)
