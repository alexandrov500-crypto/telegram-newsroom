"""Tests for Phase 4A Editorial Strategy Intelligence."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.growth_layer.strategy.growth_budget import simulate_growth_budget_shift
from app.growth_layer.strategy.opportunity_detection import detect_growth_opportunities
from app.growth_layer.strategy.portfolio_analysis import build_portfolio_analysis
from app.growth_layer.strategy.segment_allocation import recommend_content_allocation
from app.growth_layer.strategy.strategy_reporting import (
    build_editorial_strategy_snapshot,
    editorial_strategy_section,
    load_editorial_strategy_snapshot,
    persist_editorial_strategy_snapshot,
)
from app.growth_layer.strategy.strategy_scorecard import build_strategy_scorecard
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


def _portfolio_cohort() -> list[dict]:
    rows: list[dict] = []
    # technology: few posts, high performance → underinvested
    for i in range(10):
        rows.append(_row(i, "technology", err=0.85, forwards=20, engagement=0.7))
    # markets: many posts, mediocre → overinvested
    for i in range(40):
        rows.append(_row(100 + i, "markets", err=0.45, forwards=3, engagement=0.3))
    # science: moderate
    for i in range(15):
        rows.append(_row(200 + i, "science", err=0.65, forwards=8, engagement=0.5))
    return rows


# --- Portfolio analysis ---


def test_portfolio_total_posts() -> None:
    rows = _portfolio_cohort()
    pf = build_portfolio_analysis(rows)
    assert pf["total_posts"] == 65
    assert "technology" in pf["segments"]


def test_portfolio_share_of_content() -> None:
    pf = build_portfolio_analysis(_portfolio_cohort())
    tech = pf["segments"]["technology"]
    assert tech["total_posts"] == 10
    assert abs(tech["share_of_content"] - round(10 / 65 * 100, 1)) < 0.2


def test_portfolio_acquisition_share() -> None:
    pf = build_portfolio_analysis(_portfolio_cohort())
    tech = pf["segments"]["technology"]
    markets = pf["segments"]["markets"]
    tech_ratio = tech["acquisition_share"] / max(tech["share_of_content"], 0.1)
    markets_ratio = markets["acquisition_share"] / max(markets["share_of_content"], 0.1)
    assert tech_ratio > markets_ratio


def test_portfolio_roi_index() -> None:
    pf = build_portfolio_analysis(_portfolio_cohort())
    tech = pf["segments"]["technology"]
    markets = pf["segments"]["markets"]
    assert tech["roi_index"] > markets["roi_index"]


def test_portfolio_avg_metrics() -> None:
    pf = build_portfolio_analysis(_portfolio_cohort())
    tech = pf["segments"]["technology"]
    assert tech["avg_err"] is not None
    assert tech["avg_forwards"] is not None
    assert tech["acquisition_proxy_score"] > 0


def test_portfolio_empty_rows() -> None:
    pf = build_portfolio_analysis([])
    assert pf["total_posts"] == 0
    assert pf["segments"] == {}


def test_portfolio_global_baseline() -> None:
    pf = build_portfolio_analysis(_portfolio_cohort())
    assert pf["global"]["acquisition_proxy_score"] > 0


# --- Opportunity detection ---


def test_detect_underinvested_technology() -> None:
    pf = build_portfolio_analysis(_portfolio_cohort())
    opps = detect_growth_opportunities(pf)
    assert "technology" in opps
    assert opps["technology"]["type"] == "UNDERINVESTED"
    assert opps["technology"]["opportunity_score"] > 0


def test_detect_overinvested_markets() -> None:
    pf = build_portfolio_analysis(_portfolio_cohort())
    opps = detect_growth_opportunities(pf)
    assert "markets" in opps
    assert opps["markets"]["type"] == "OVERINVESTED"


def test_opportunity_score_range() -> None:
    opps = detect_growth_opportunities(build_portfolio_analysis(_portfolio_cohort()))
    for data in opps.values():
        assert 0 <= data["opportunity_score"] <= 100


def test_opportunity_skips_tiny_segments() -> None:
    rows = [_row(1, "crypto", err=0.9, forwards=30)] * 2
    opps = detect_growth_opportunities(build_portfolio_analysis(rows))
    assert "crypto" not in opps


# --- Allocation ---


def test_allocation_sums_to_100() -> None:
    pf = build_portfolio_analysis(_portfolio_cohort())
    opps = detect_growth_opportunities(pf)
    alloc = recommend_content_allocation(pf, opps)
    total = sum(v["recommended_share"] for v in alloc.values())
    assert abs(total - 100.0) < 0.5


def test_allocation_increases_underinvested() -> None:
    pf = build_portfolio_analysis(_portfolio_cohort())
    opps = detect_growth_opportunities(pf)
    alloc = recommend_content_allocation(pf, opps)
    if "technology" in alloc:
        assert alloc["technology"]["recommended_share"] >= alloc["technology"]["current_share"]


def test_allocation_decreases_overinvested() -> None:
    pf = build_portfolio_analysis(_portfolio_cohort())
    opps = detect_growth_opportunities(pf)
    alloc = recommend_content_allocation(pf, opps)
    if "markets" in alloc:
        assert alloc["markets"]["recommended_share"] <= alloc["markets"]["current_share"]


def test_allocation_bounded_shift() -> None:
    pf = build_portfolio_analysis(_portfolio_cohort())
    opps = detect_growth_opportunities(pf)
    alloc = recommend_content_allocation(pf, opps, max_shift_pct=10.0)
    for seg, data in alloc.items():
        assert abs(data["delta"]) <= 10.1


def test_allocation_empty_portfolio() -> None:
    assert recommend_content_allocation({"segments": {}}) == {}


# --- Growth budget simulation ---


def test_simulate_shift_positive_delta() -> None:
    pf = build_portfolio_analysis(_portfolio_cohort())
    sim = simulate_growth_budget_shift(pf, from_segment="markets", to_segment="technology", delta_percent=10.0)
    assert sim["explainable"] is True
    assert sim["expected_acquisition_delta"] > 0


def test_simulate_shift_unknown_segment() -> None:
    pf = build_portfolio_analysis(_portfolio_cohort())
    sim = simulate_growth_budget_shift(pf, from_segment="unknown", to_segment="technology", delta_percent=5.0)
    assert sim["explainable"] is False
    assert sim["expected_acquisition_delta"] == 0.0


def test_simulate_shift_includes_roi_indices() -> None:
    pf = build_portfolio_analysis(_portfolio_cohort())
    sim = simulate_growth_budget_shift(pf, from_segment="markets", to_segment="technology", delta_percent=5.0)
    assert sim["source_roi_index"] is not None
    assert sim["destination_roi_index"] is not None


# --- Strategy scorecard ---


def test_scorecard_structure() -> None:
    pf = build_portfolio_analysis(_portfolio_cohort())
    opps = detect_growth_opportunities(pf)
    alloc = recommend_content_allocation(pf, opps)
    sc = build_strategy_scorecard(pf, opps, alloc)
    assert 0 <= sc["strategy_score"] <= 100
    assert "technology" in sc["best_segments"]
    assert isinstance(sc["underinvested_segments"], list)
    assert isinstance(sc["overinvested_segments"], list)


def test_scorecard_identifies_under_over() -> None:
    pf = build_portfolio_analysis(_portfolio_cohort())
    opps = detect_growth_opportunities(pf)
    sc = build_strategy_scorecard(pf, opps)
    assert "technology" in sc["underinvested_segments"] or "markets" in sc["overinvested_segments"]


# --- Snapshot & reporting ---


def test_build_editorial_strategy_snapshot() -> None:
    snap = build_editorial_strategy_snapshot(_portfolio_cohort())
    assert "portfolio" in snap
    assert "opportunities" in snap
    assert "allocation" in snap
    assert "scorecard" in snap
    assert snap["scorecard"]["strategy_score"] >= 0


def test_persist_and_load_snapshot(tmp_path: Path) -> None:
    snap = build_editorial_strategy_snapshot(_portfolio_cohort())
    persist_editorial_strategy_snapshot(tmp_path, snap)
    loaded = load_editorial_strategy_snapshot(tmp_path)
    assert loaded["scorecard"]["strategy_score"] == snap["scorecard"]["strategy_score"]


def test_editorial_strategy_section() -> None:
    snap = build_editorial_strategy_snapshot(_portfolio_cohort())
    lines = editorial_strategy_section(snap)
    text = "\n".join(lines)
    assert "EDITORIAL STRATEGY" in text
    assert "Best ROI segment" in text


def test_weekly_report_includes_strategy_section() -> None:
    snap = build_editorial_strategy_snapshot(_portfolio_cohort())
    html = build_weekly_growth_report(week_rows=[], all_rows=[], strategy_snapshot=snap)
    assert "EDITORIAL STRATEGY" in html


def test_strategy_section_empty() -> None:
    lines = editorial_strategy_section({})
    assert "Недостаточно данных" in "\n".join(lines)


def test_snapshot_simulation_present() -> None:
    snap = build_editorial_strategy_snapshot(_portfolio_cohort())
    assert "simulations" in snap
    if snap.get("expected_growth_impact"):
        assert "expected_acquisition_delta" in snap["expected_growth_impact"]


def test_roi_index_normalized_to_one() -> None:
    rows = [_row(i, "general_news", err=0.5, forwards=5) for i in range(20)]
    pf = build_portfolio_analysis(rows)
    assert abs(pf["segments"]["general_news"]["roi_index"] - 1.0) < 0.01


def test_allocation_json_serializable() -> None:
    snap = build_editorial_strategy_snapshot(_portfolio_cohort())
    json.dumps(snap)
