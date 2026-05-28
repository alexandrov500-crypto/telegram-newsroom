"""Runtime health monitor and adaptive protection."""

from __future__ import annotations

import json

import pytest

from app.observability.runtime_health import (
    collect_health_snapshot,
    persist_health_snapshot,
    reset_runtime_health_for_tests,
)
from app.observability.runtime_protection import (
    RuntimeHealthLevel,
    autonomous_publish_blocked,
    classify_degradation,
    evaluate_and_apply_protection,
    load_protection_state,
    pipeline_interval_multiplier,
    try_automatic_recovery,
)
from app.observability.runtime_resilience_report import evaluate_public_go_resilience


@pytest.fixture(autouse=True)
def _reset_health():
    reset_runtime_health_for_tests()
    yield
    reset_runtime_health_for_tests()


def test_classify_normal_empty_flags():
    level, flags = classify_degradation({"degradation_flags": []})
    assert level == RuntimeHealthLevel.NORMAL
    assert flags == []


def test_classify_critical_multiple_flags():
    snap = {
        "degradation_flags": ["memory_drift_high", "tick_duration_p95_high"],
    }
    level, _ = classify_degradation(snap)
    assert level == RuntimeHealthLevel.CRITICAL


def test_classify_elevated_single_flag():
    level, _ = classify_degradation({"degradation_flags": ["retry_rate_high"]})
    assert level == RuntimeHealthLevel.ELEVATED


def test_health_snapshot_persist(tmp_path):
    snap = collect_health_snapshot()
    persist_health_snapshot(str(tmp_path), snap)
    lines = (tmp_path / "runtime_health.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1
    row = json.loads(lines[0])
    assert "timestamp" in row
    assert "rss_mb" in row or row.get("rss_mb") is None


def test_protection_transition_to_degraded(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNTIME_HEALTH_RSS_DRIFT_MB", "1")
    snap = {
        "degradation_flags": ["retry_rate_high", "openai_latency_high"],
        "rss_drift_mb": 10,
    }
    level, _ = classify_degradation(snap)
    assert level == RuntimeHealthLevel.DEGRADED


def test_critical_blocks_autonomous_publish(tmp_path):
    from app.observability.runtime_protection import _transition, load_protection_state

    state = load_protection_state(str(tmp_path))
    _transition(str(tmp_path), state, RuntimeHealthLevel.CRITICAL, ["test"])
    assert autonomous_publish_blocked(str(tmp_path)) is True


def test_degraded_interval_multiplier(tmp_path):
    from app.observability.runtime_protection import _transition, load_protection_state

    state = load_protection_state(str(tmp_path))
    _transition(str(tmp_path), state, RuntimeHealthLevel.DEGRADED, ["test"])
    assert pipeline_interval_multiplier(str(tmp_path)) >= 1.2


def test_recovery_requires_streak(tmp_path, monkeypatch):
    from app.observability.runtime_protection import _transition

    monkeypatch.setenv("RUNTIME_PROTECTION_RECOVERY_SAMPLES", "3")
    state = load_protection_state(str(tmp_path))
    _transition(str(tmp_path), state, RuntimeHealthLevel.ELEVATED, ["elevated"])
    for i in range(3):
        for _ in range(5):
            snap = {"degradation_flags": [], "rss_drift_mb": 0, "p95_tick_duration_sec": 1}
            persist_health_snapshot(str(tmp_path), snap)
        ok = try_automatic_recovery(str(tmp_path), {"degradation_flags": []})
        if i < 2:
            assert ok is False
        else:
            assert ok is True
    assert load_protection_state(str(tmp_path))["current_state"] == RuntimeHealthLevel.NORMAL.value


def test_public_go_fails_on_critical_history(tmp_path):
    from app.observability.runtime_protection import save_protection_state

    state = {
        "current_state": "normal",
        "transition_history": [{"from": "normal", "to": "critical", "at": "2026-01-01T00:00:00Z"}],
        "protection_activation_count": 1,
        "recovery_count": 0,
    }
    save_protection_state(str(tmp_path), state)
    fails, _ = evaluate_public_go_resilience(tmp_path)
    assert any("critical" in f for f in fails)


def test_evaluate_and_apply_persists_state(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNTIME_HEALTH_RSS_DRIFT_MB", "99999")
    out = evaluate_and_apply_protection(str(tmp_path))
    assert "snapshot" in out
    assert (_path := tmp_path / "runtime_protection_state.json").is_file()
    data = json.loads(_path.read_text())
    assert "current_state" in data
