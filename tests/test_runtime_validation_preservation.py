from __future__ import annotations

from bot.editorial.runtime_validation.preservation import (
    build_monthly_stability_review,
    identify_dead_complexity_signals,
)


def _week(ok: bool = True, growth: float = 0.2, lines: float = 2) -> dict:
    return {
        "infrastructure_validation_ok": ok,
        "persistence": {"persistence_growth_rate": growth},
        "digest": {"digest_line_count": lines},
        "calmness": {"hidden_entropy_observed": False},
    }


def test_monthly_stable_verdict() -> None:
    review = build_monthly_stability_review(
        weekly_history=[_week() for _ in range(4)],
        current_report={
            "infrastructure_validation_ok": True,
            "persistence": {"bounded_persistence_ok": True},
            "telemetry": {"canonical_telemetry_stability": True},
            "operational_aging": {"long_horizon_calm": True},
        },
        dead_complexity={"manual_review_recommended": False},
    )
    assert review["monthly_verdict"] == "stable"


def test_monthly_surgical_when_boundedness_fails() -> None:
    review = build_monthly_stability_review(
        weekly_history=[_week()],
        current_report={
            "persistence": {"bounded_persistence_ok": False},
            "telemetry": {},
        },
    )
    assert review["monthly_verdict"] == "surgical_maintenance_required"


def test_monthly_observe_on_drift() -> None:
    review = build_monthly_stability_review(
        weekly_history=[_week(growth=0.8), _week(growth=0.85)],
        current_report={
            "persistence": {"bounded_persistence_ok": True},
            "telemetry": {"canonical_telemetry_stability": True},
        },
    )
    assert review["monthly_verdict"] in ("observe", "surgical_maintenance_required")


def test_dead_complexity_hints_advisory() -> None:
    dead = identify_dead_complexity_signals(
        ctx={"flow_certification": None, "flow_closure": None, "flow_legacy": None},
        metrics={"operational_memory": {"touch": {"signatures": []}}},
    )
    assert "dead_complexity_hints" in dead
    assert dead["manual_review_recommended"] is False or isinstance(
        dead["manual_review_recommended"],
        bool,
    )
