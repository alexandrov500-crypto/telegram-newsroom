from __future__ import annotations

from utils.runtime_anomalies import RuntimeAnomaly, detect_runtime_anomalies


def test_detect_excessive_retries():
    snap = {"metrics": {"counters": {"openai_retries": 50}}}
    a = detect_runtime_anomalies(snap)
    assert any(x.code == "openai.excessive_retries" for x in a)


def test_detect_scheduler_stuck_wall():
    snap = {"scheduler": {"tick_in_progress": True, "last_scheduler_wall_sec": 1000.0}}
    a = detect_runtime_anomalies(snap)
    assert any(x.code == "scheduler.tick_stalled" for x in a)


def test_detect_openai_failures():
    snap = {"metrics": {"counters": {"openai_failures": 12}}}
    a = detect_runtime_anomalies(snap)
    assert any(x.code == "openai.repeated_failures" for x in a)


def test_empty_metrics_safe():
    a = detect_runtime_anomalies({})
    assert isinstance(a, list)
    assert all(isinstance(x, RuntimeAnomaly) for x in a)
