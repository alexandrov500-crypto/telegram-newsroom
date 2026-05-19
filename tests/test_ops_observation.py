from __future__ import annotations

from bot.ops_observation.anomalies import detect_anomalies
from bot.ops_observation.baseline import update_baseline


def test_no_anomalies_healthy_pulse() -> None:
    pulse = {
        "event_loop_lag_max": 0.02,
        "stalled_loops": [],
        "recovery_attempt_count": 0,
        "runtime_profile": "minimal_pilot",
    }
    assert detect_anomalies(pulse) == []


def test_critical_stalled_loops() -> None:
    pulse = {
        "event_loop_lag_max": 0.01,
        "stalled_loops": ["rss-ingestion"],
        "recovery_attempt_count": 0,
        "runtime_profile": "minimal_pilot",
    }
    codes = [a["code"] for a in detect_anomalies(pulse)]
    assert "stalled_loops" in codes


def test_baseline_updates() -> None:
    b = update_baseline({}, {"event_loop_lag_max": 0.1, "publishes_this_hour": 2, "timestamp": "t"})
    assert b["pulse_count"] == 1
    assert b["event_loop_lag_max"]["max"] == 0.1
