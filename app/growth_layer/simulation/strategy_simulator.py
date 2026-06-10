"""Compare multiple editorial strategy scenarios."""

from __future__ import annotations

from typing import Any

from app.growth_layer.simulation.what_if_engine import run_what_if_simulation


def simulate_strategy(
    base_strategy: dict[str, Any],
    scenarios: dict[str, Any] | list[dict[str, Any]],
    portfolio: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Run what-if for each scenario and rank by expected acquisition impact.
    """
    pf = portfolio or base_strategy.get("portfolio") or {}
    if isinstance(scenarios, dict):
        scenario_list = scenarios.get("scenarios") if isinstance(scenarios.get("scenarios"), list) else []
        base_allocation = scenarios.get("base_allocation") if isinstance(scenarios.get("base_allocation"), dict) else None
    else:
        scenario_list = list(scenarios)
        base_allocation = None

    if base_allocation is None:
        from app.growth_layer.simulation.scenario_builder import extract_current_allocation

        base_allocation = extract_current_allocation(base_strategy)

    results: list[dict[str, Any]] = []
    for scenario in scenario_list:
        if not isinstance(scenario, dict):
            continue
        projection = run_what_if_simulation(
            scenario,
            pf,
            base_allocation=base_allocation,
        )
        results.append(projection)

    ranked = sorted(
        results,
        key=lambda r: float(r.get("expected_acquisition_delta") or 0),
        reverse=True,
    )
    ranking = [
        {
            "scenario": r.get("scenario"),
            "label": r.get("label"),
            "impact": r.get("expected_acquisition_delta"),
            "expected_err_change": r.get("expected_err_change"),
            "risk_score": r.get("risk_score"),
        }
        for r in ranked
    ]
    best = ranking[0]["scenario"] if ranking else None

    return {
        "best_scenario": best,
        "ranking": ranking,
        "projections": ranked,
        "base_allocation": base_allocation,
        "scenario_count": len(ranking),
    }
