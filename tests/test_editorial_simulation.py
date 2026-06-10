"""Tests for Phase 4C Editorial Simulation Layer."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.growth_layer.simulation.impact_estimator import estimate_strategy_impact
from app.growth_layer.simulation.portfolio_simulation import simulate_portfolio_shift
from app.growth_layer.simulation.scenario_builder import build_strategy_scenarios, extract_current_allocation
from app.growth_layer.simulation.simulation_report import (
    build_editorial_simulation_snapshot,
    check_scenario_alignment,
    editorial_simulation_section,
    format_scenario_report,
    load_editorial_simulation_snapshot,
    persist_editorial_simulation_snapshot,
    simulate_top_scenarios,
)
from app.growth_layer.simulation.strategy_simulator import simulate_strategy
from app.growth_layer.simulation.what_if_engine import run_what_if_simulation
from app.growth_layer.strategy.strategy_reporting import build_editorial_strategy_snapshot
from app.growth_layer.validation.acquisition_proxy import compute_acquisition_components
from app.growth_layer.validation.weekly_report import build_weekly_growth_report


def _row(
    draft_id: int,
    segment: str,
    *,
    err: float = 0.5,
    forwards: int = 5,
    engagement: float = 0.4,
) -> dict:
    comp = compute_acquisition_components(forwards=float(forwards), err=err, engagement=engagement)
    return {
        "draft_id": draft_id,
        "content_segment": segment,
        "format_profile": "growth_brief",
        "validation_status": "FINAL",
        "actual_err": err,
        "actual_forwards": forwards,
        "actual_engagement": engagement,
        **comp,
        "published_at": datetime.now(timezone.utc).isoformat(),
    }


def _cohort() -> list[dict]:
    rows: list[dict] = []
    for i in range(10):
        rows.append(_row(i, "technology", err=0.85, forwards=20, engagement=0.7))
    for i in range(40):
        rows.append(_row(100 + i, "markets", err=0.45, forwards=3, engagement=0.3))
    for i in range(15):
        rows.append(_row(200 + i, "science", err=0.65, forwards=8, engagement=0.5))
    return rows


def _strategy_snapshot() -> dict:
    return build_editorial_strategy_snapshot(_cohort())


def _portfolio() -> dict:
    return _strategy_snapshot()["portfolio"]


def _base_strategy() -> dict:
    snap = _strategy_snapshot()
    return {"portfolio": snap["portfolio"], "allocation": snap["allocation"]}


# --- Scenario builder ---


def test_build_scenarios_returns_five() -> None:
    out = build_strategy_scenarios(_base_strategy())
    assert len(out["scenarios"]) == 5
    names = {s["name"] for s in out["scenarios"]}
    assert names == {"tech_boost", "markets_cut", "balanced", "aggressive_growth", "conservative"}


def test_scenario_allocations_sum_to_100() -> None:
    out = build_strategy_scenarios(_base_strategy())
    for scenario in out["scenarios"]:
        total = sum(scenario["allocation"].values())
        assert abs(total - 100.0) < 0.2


def test_tech_boost_increases_technology_share() -> None:
    base = _base_strategy()
    out = build_strategy_scenarios(base)
    current = out["base_allocation"]["technology"]
    tech = next(s for s in out["scenarios"] if s["name"] == "tech_boost")
    assert tech["allocation"]["technology"] > current


def test_markets_cut_decreases_markets_share() -> None:
    out = build_strategy_scenarios(_base_strategy())
    current = out["base_allocation"]["markets"]
    markets = next(s for s in out["scenarios"] if s["name"] == "markets_cut")
    assert markets["allocation"]["markets"] < current


def test_balanced_equal_shares() -> None:
    out = build_strategy_scenarios(_base_strategy())
    balanced = next(s for s in out["scenarios"] if s["name"] == "balanced")
    vals = list(balanced["allocation"].values())
    assert max(vals) - min(vals) < 2.0


def test_extract_current_allocation_from_portfolio() -> None:
    snap = _strategy_snapshot()
    alloc = extract_current_allocation({"portfolio": snap["portfolio"]})
    assert "technology" in alloc
    assert abs(sum(alloc.values()) - 100.0) < 0.2


def test_scenarios_empty_without_data() -> None:
    out = build_strategy_scenarios({})
    assert out["scenarios"] == []


# --- What-if engine ---


def test_what_if_positive_for_tech_boost() -> None:
    scenarios = build_strategy_scenarios(_base_strategy())
    tech = next(s for s in scenarios["scenarios"] if s["name"] == "tech_boost")
    result = run_what_if_simulation(tech, _portfolio(), base_allocation=scenarios["base_allocation"])
    assert result["expected_acquisition_delta"] > 0
    assert result["explainable"] is True


def test_what_if_deterministic() -> None:
    scenarios = build_strategy_scenarios(_base_strategy())
    tech = next(s for s in scenarios["scenarios"] if s["name"] == "tech_boost")
    a = run_what_if_simulation(tech, _portfolio(), base_allocation=scenarios["base_allocation"])
    b = run_what_if_simulation(tech, _portfolio(), base_allocation=scenarios["base_allocation"])
    assert a == b


def test_what_if_risk_score_bounded() -> None:
    scenarios = build_strategy_scenarios(_base_strategy())
    for scenario in scenarios["scenarios"]:
        r = run_what_if_simulation(scenario, _portfolio(), base_allocation=scenarios["base_allocation"])
        assert 0.0 <= r["risk_score"] <= 1.0


def test_what_if_includes_err_change() -> None:
    scenarios = build_strategy_scenarios(_base_strategy())
    tech = next(s for s in scenarios["scenarios"] if s["name"] == "tech_boost")
    r = run_what_if_simulation(tech, _portfolio(), base_allocation=scenarios["base_allocation"])
    assert "expected_err_change" in r


def test_what_if_empty_scenario() -> None:
    r = run_what_if_simulation({"name": "empty"}, _portfolio())
    assert r["expected_acquisition_delta"] == 0.0
    assert r["explainable"] is False


# --- Strategy simulator ---


def test_simulate_strategy_best_has_highest_impact() -> None:
    base = _base_strategy()
    scenarios = build_strategy_scenarios(base)
    result = simulate_strategy(base, scenarios, _portfolio())
    assert result["best_scenario"] in {"tech_boost", "balanced", "aggressive_growth"}
    assert len(result["ranking"]) == 5
    top_impact = float(result["ranking"][0]["impact"])
    assert top_impact > 0


def test_simulate_strategy_ranking_sorted() -> None:
    base = _base_strategy()
    scenarios = build_strategy_scenarios(base)
    result = simulate_strategy(base, scenarios, _portfolio())
    impacts = [float(r["impact"]) for r in result["ranking"]]
    assert impacts == sorted(impacts, reverse=True)


def test_simulate_strategy_ranking_has_impact() -> None:
    result = simulate_strategy(_base_strategy(), build_strategy_scenarios(_base_strategy()), _portfolio())
    assert all("impact" in r for r in result["ranking"])


def test_simulate_top_scenarios_hook() -> None:
    snap = _strategy_snapshot()
    sim = simulate_top_scenarios(snap)
    assert sim["best_scenario"] in {"tech_boost", "balanced", "aggressive_growth"}
    assert sim["scenario_count"] == 5
    assert float(sim["ranking"][0]["impact"]) > 0


# --- Portfolio simulation ---


def test_portfolio_shift_acquisition_delta() -> None:
    scenarios = build_strategy_scenarios(_base_strategy())
    from_alloc = scenarios["base_allocation"]
    to_alloc = next(s for s in scenarios["scenarios"] if s["name"] == "tech_boost")["allocation"]
    shift = simulate_portfolio_shift(from_alloc, to_alloc, _portfolio())
    assert shift["expected_acquisition_delta"] > 0
    assert "segment_pressure_change" in shift


def test_portfolio_shift_pressure_increased_technology() -> None:
    scenarios = build_strategy_scenarios(_base_strategy())
    from_alloc = scenarios["base_allocation"]
    to_alloc = next(s for s in scenarios["scenarios"] if s["name"] == "tech_boost")["allocation"]
    shift = simulate_portfolio_shift(from_alloc, to_alloc, _portfolio())
    assert "technology" in shift["pressure_increased"]


def test_portfolio_shift_normalizes_allocations() -> None:
    shift = simulate_portfolio_shift({"technology": 50, "markets": 50}, {"technology": 60, "markets": 40}, _portfolio())
    assert abs(sum(shift["from_allocation"].values()) - 100.0) < 0.2
    assert abs(sum(shift["to_allocation"].values()) - 100.0) < 0.2


# --- Impact estimator ---


def test_estimate_strategy_impact_labels() -> None:
    scenarios = build_strategy_scenarios(_base_strategy())
    tech = next(s for s in scenarios["scenarios"] if s["name"] == "tech_boost")
    impact = estimate_strategy_impact(tech, _portfolio(), base_allocation=scenarios["base_allocation"])
    assert impact["confidence"] in {"LOW", "MEDIUM", "HIGH"}
    assert impact["risk"] in {"LOW", "MEDIUM", "HIGH"}
    assert impact["acquisition_gain"] > 0


def test_estimate_strategy_impact_empty() -> None:
    impact = estimate_strategy_impact({}, _portfolio())
    assert impact["explainable"] is False


def test_high_confidence_with_large_cohort() -> None:
    rows: list[dict] = []
    n = 0
    for _ in range(4):
        for row in _cohort():
            rows.append({**row, "draft_id": n})
            n += 1
    snap = build_editorial_simulation_snapshot(build_editorial_strategy_snapshot(rows))
    assert snap["best_scenario_impact"]["confidence"] in {"MEDIUM", "HIGH"}


# --- Simulation report ---


def test_format_scenario_report_contains_fields() -> None:
    scenarios = build_strategy_scenarios(_base_strategy())
    tech = next(s for s in scenarios["scenarios"] if s["name"] == "tech_boost")
    proj = run_what_if_simulation(tech, _portfolio(), base_allocation=scenarios["base_allocation"])
    text = format_scenario_report(proj, portfolio=_portfolio())
    assert "SCENARIO:" in text
    assert "Expected acquisition:" in text
    assert "Risk:" in text
    assert "KEY DRIVER:" in text


def test_build_editorial_simulation_snapshot() -> None:
    snap = build_editorial_simulation_snapshot(_strategy_snapshot())
    assert snap["best_scenario"] in {"tech_boost", "balanced", "aggressive_growth"}
    assert snap["ranking"]
    assert snap["risk_assessment"]["risk_label"] in {"LOW", "MEDIUM", "HIGH"}


def test_build_simulation_from_rows() -> None:
    snap = build_editorial_simulation_snapshot(rows=_cohort())
    assert snap["best_scenario"] is not None


def test_persist_and_load_snapshot(tmp_path: Path) -> None:
    snap = build_editorial_simulation_snapshot(_strategy_snapshot())
    persist_editorial_simulation_snapshot(tmp_path, snap)
    loaded = load_editorial_simulation_snapshot(tmp_path)
    assert loaded["best_scenario"] == snap["best_scenario"]
    raw = json.loads((tmp_path / "editorial_simulation.json").read_text(encoding="utf-8"))
    assert raw["ranking"]


def test_editorial_simulation_section() -> None:
    snap = build_editorial_simulation_snapshot(_strategy_snapshot())
    lines = editorial_simulation_section(snap)
    text = "\n".join(lines)
    assert "EDITORIAL SIMULATION" in text
    assert "Best scenario" in text
    assert "tech_boost" in text.lower() or "Tech Boost" in text


def test_weekly_report_includes_simulation_section() -> None:
    snap = build_editorial_simulation_snapshot(_strategy_snapshot())
    html = build_weekly_growth_report(
        week_rows=[],
        all_rows=_cohort(),
        simulation_snapshot=snap,
    )
    assert "EDITORIAL SIMULATION" in html


def test_check_scenario_alignment_exact_match() -> None:
    sim = build_editorial_simulation_snapshot(_strategy_snapshot())
    result = check_scenario_alignment(sim, {"scenario": sim["best_scenario"]})
    assert result["aligned"] is True
    assert result["reason"] == "exact_scenario_match"


def test_check_scenario_alignment_segment_boost() -> None:
    sim = build_editorial_simulation_snapshot(_strategy_snapshot())
    result = check_scenario_alignment(sim, {"segment": "technology"})
    assert result["aligned"] is True


def test_check_scenario_alignment_mismatch() -> None:
    sim = build_editorial_simulation_snapshot(_strategy_snapshot())
    result = check_scenario_alignment(sim, {"scenario": "markets_cut"})
    if sim["best_scenario"] != "markets_cut":
        assert result["aligned"] is False


def test_check_scenario_alignment_no_data() -> None:
    result = check_scenario_alignment({}, None)
    assert result["aligned"] is True
    assert result["reason"] == "no_simulation_data"


def test_aggressive_growth_beats_conservative() -> None:
    base = _base_strategy()
    scenarios = build_strategy_scenarios(base)
    result = simulate_strategy(base, scenarios, _portfolio())
    aggressive = next(r for r in result["ranking"] if r["scenario"] == "aggressive_growth")
    conservative = next(r for r in result["ranking"] if r["scenario"] == "conservative")
    assert float(aggressive["impact"]) >= float(conservative["impact"])


def test_strategy_snapshot_includes_scenario_preview() -> None:
    snap = _strategy_snapshot()
    preview = snap.get("scenario_simulation") or {}
    assert preview.get("best_scenario") in {"tech_boost", "balanced", "aggressive_growth", None}
    assert preview.get("ranking")
