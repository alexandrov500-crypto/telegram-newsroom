from __future__ import annotations

from pathlib import Path

from bot.ops_resilience.backpressure import apply_backpressure
from bot.ops_resilience.context import get_resilience_context, should_defer_analytics
from bot.ops_resilience.coordinator import evaluate_resilience_tick
from bot.ops_resilience.dependencies import classify_dependencies
from bot.ops_resilience.failure_budget import compute_failure_budgets
from bot.ops_resilience.recovery_quality import evaluate_recovery_quality
from bot.ops_resilience.state_machine import resolve_posture
from bot.ops_resilience.types import OperationalPosture
from bot.storage.db import init_database


def test_dependency_classification() -> None:
    pulse = {
        "event_loop_lag_max": 0.8,
        "recovery_attempt_count": 7,
        "stalled_loops": ["rss"],
        "loop_health": {"rss_loop_duration_avg": 50},
        "http": {},
        "anomalies": [{"level": "warning"}],
    }
    deps = classify_dependencies(pulse=pulse)
    assert deps["rss_ingestion"]["band"] in ("degraded", "unstable")
    assert deps["background_maintenance"]["band"] in ("degraded", "unstable")


def test_posture_observation_only() -> None:
    deps = {"sqlite": {"band": "critical"}}
    posture, _ = resolve_posture(
        dependencies=deps,
        failure_budgets={"instability_ratio": 0.95, "recovery_storm": False},
        recovery_quality={},
        soft_degraded=False,
    )
    assert posture == OperationalPosture.OBSERVATION_ONLY.value


def test_backpressure_defers_analytics() -> None:
    apply_backpressure(
        [{"condition": "lag", "response": "pause_background_analytics"}],
        posture="protected",
    )
    assert should_defer_analytics()
    ctx = get_resilience_context()
    assert ctx.pause_background_analytics


def test_failure_budget_recovery_storm() -> None:
    budgets = compute_failure_budgets(
        pulse={"event_loop_lag_max": 1.0, "recovery_attempt_count": 8, "anomalies": []},
        events=[],
        recovery_log=[],
    )
    assert budgets["recovery_storm"] is True


def test_recovery_quality_storm() -> None:
    log = [
        {"subsystem": "runtime", "outcome": "repeated"},
        {"subsystem": "runtime", "outcome": "repeated"},
        {"subsystem": "runtime", "outcome": "repeated"},
        {"subsystem": "runtime", "outcome": "repeated"},
    ]
    q = evaluate_recovery_quality(log)
    assert q["recovery_storm"] is True


def test_evaluate_resilience_tick(tmp_path: Path) -> None:
    db = init_database(tmp_path / "resilience.db")
    snap = evaluate_resilience_tick(
        db_path=db,
        pulse={
            "event_loop_lag_max": 0.05,
            "recovery_attempt_count": 0,
            "stalled_loops": [],
            "anomalies": [],
            "http": {},
            "loop_health": {},
        },
        persist=True,
    )
    assert snap["posture"] in {p.value for p in OperationalPosture}
    assert "guidance" in snap
