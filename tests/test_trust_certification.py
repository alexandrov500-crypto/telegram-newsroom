"""Trust certification, regression, evolution gates."""

from __future__ import annotations

from ops.trust.autonomous_validation import run_autonomous_validation
from ops.trust.behavior_regression import run_behavior_regression
from ops.trust.evolution_gates import validate_evolution_change
from ops.trust.evolution_journal import append_evolution_event, query_evolution_history
from ops.trust.drift_baselines import assess_drift_vs_baseline


def test_behavior_regression_baseline(ephemeral_newsroom_settings) -> None:
    rd = ephemeral_newsroom_settings.runtime_state_dir
    r1 = run_behavior_regression(rd, window_hours=24.0, save_baseline=True)
    assert r1.get("passed") is True
    r2 = run_behavior_regression(rd, window_hours=24.0)
    assert r2.get("diff_count", 0) == 0


def test_evolution_journal(ephemeral_newsroom_settings) -> None:
    rd = ephemeral_newsroom_settings.runtime_state_dir
    append_evolution_event(rd, event_type="test", summary="unit test", correlation_id="t1")
    rows = query_evolution_history(rd, limit=5, event_type="test")
    assert rows and rows[0]["correlation_id"] == "t1"


def test_evolution_gate_policy(ephemeral_newsroom_settings) -> None:
    gate = validate_evolution_change(
        ephemeral_newsroom_settings,
        change_type="policy",
        payload={"rules": [{"id": "x", "enabled": True, "type": "test"}]},
    )
    assert "ok" in gate


def test_autonomous_validation(ephemeral_newsroom_settings) -> None:
    rep = run_autonomous_validation(ephemeral_newsroom_settings, ephemeral_newsroom_settings.runtime_state_dir)
    assert "checks" in rep
    assert len(rep["checks"]) >= 5


def test_drift_baselines(ephemeral_newsroom_settings) -> None:
    assess = assess_drift_vs_baseline(ephemeral_newsroom_settings.runtime_state_dir)
    assert "ema_baseline" in assess
