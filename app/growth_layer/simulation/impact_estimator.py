"""Strategy impact estimation with confidence and risk labels."""

from __future__ import annotations

from typing import Any

from app.growth_layer.simulation.what_if_engine import run_what_if_simulation


def _confidence_label(*, total_posts: int, scenario_count: int) -> str:
    if total_posts >= 50 and scenario_count >= 3:
        return "HIGH"
    if total_posts >= 20:
        return "MEDIUM"
    return "LOW"


def _risk_label(risk_score: float) -> str:
    if risk_score <= 0.25:
        return "LOW"
    if risk_score <= 0.55:
        return "MEDIUM"
    return "HIGH"


def estimate_strategy_impact(
    strategy: dict[str, Any],
    portfolio: dict[str, Any] | None = None,
    *,
    base_allocation: dict[str, float] | None = None,
) -> dict[str, Any]:
    """
    Summarize expected impact of a single strategy / scenario allocation.
    """
    pf = portfolio or strategy.get("portfolio") or {}
    allocation = strategy.get("allocation") if isinstance(strategy.get("allocation"), dict) else strategy
    if not isinstance(allocation, dict) or not allocation:
        return {
            "acquisition_gain": 0.0,
            "expected_err_change": 0.0,
            "confidence": "LOW",
            "risk": "HIGH",
            "explainable": False,
        }

    scenario = {
        "name": str(strategy.get("name") or "strategy"),
        "allocation": allocation,
    }
    projection = run_what_if_simulation(scenario, pf, base_allocation=base_allocation)
    total_posts = int(pf.get("total_posts") or 0)
    risk_score = float(projection.get("risk_score") or 0)

    return {
        "scenario": scenario["name"],
        "acquisition_gain": projection.get("expected_acquisition_delta"),
        "expected_err_change": projection.get("expected_err_change"),
        "confidence": _confidence_label(total_posts=total_posts, scenario_count=1),
        "risk": _risk_label(risk_score),
        "risk_score": risk_score,
        "method": projection.get("method"),
        "explainable": True,
    }
