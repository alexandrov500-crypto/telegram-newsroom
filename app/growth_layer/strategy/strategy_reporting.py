"""Editorial strategy reporting and runtime snapshots."""

from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any

from app.growth_layer.strategy.growth_budget import simulate_growth_budget_shift
from app.growth_layer.strategy.opportunity_detection import detect_growth_opportunities
from app.growth_layer.strategy.portfolio_analysis import build_portfolio_analysis
from app.growth_layer.strategy.segment_allocation import recommend_content_allocation
from app.growth_layer.strategy.strategy_scorecard import build_strategy_scorecard


def build_editorial_strategy_snapshot(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Full Phase 4A strategy snapshot from validation rows."""
    portfolio = build_portfolio_analysis(rows)
    opportunities = detect_growth_opportunities(portfolio)
    allocation = recommend_content_allocation(portfolio, opportunities)
    scorecard = build_strategy_scorecard(portfolio, opportunities, allocation)

    simulations: list[dict[str, Any]] = []
    under = scorecard.get("underinvested_segments") or []
    over = scorecard.get("overinvested_segments") or []
    if under and over:
        simulations.append(
            simulate_growth_budget_shift(
                portfolio,
                from_segment=str(over[0]),
                to_segment=str(under[0]),
                delta_percent=min(10.0, float(allocation.get(under[0], {}).get("delta") or 5.0)),
            )
        )
    elif under:
        best = (scorecard.get("best_segments") or [under[0]])[0]
        if best != under[0]:
            simulations.append(
                simulate_growth_budget_shift(
                    portfolio,
                    from_segment=str(best),
                    to_segment=str(under[0]),
                    delta_percent=5.0,
                )
            )

    return {
        "portfolio": portfolio,
        "opportunities": opportunities,
        "allocation": allocation,
        "scorecard": scorecard,
        "simulations": simulations,
        "expected_growth_impact": simulations[0] if simulations else {},
        "scenario_simulation": _optional_scenario_simulation(portfolio, allocation, scorecard),
    }


def _optional_scenario_simulation(
    portfolio: dict[str, Any],
    allocation: dict[str, Any],
    scorecard: dict[str, Any],
) -> dict[str, Any]:
    """Phase 4C hook: lightweight top-scenario preview on strategy snapshot."""
    try:
        from app.growth_layer.simulation.simulation_report import simulate_top_scenarios

        snap = {"portfolio": portfolio, "allocation": allocation, "scorecard": scorecard}
        result = simulate_top_scenarios(snap)
        return {
            "best_scenario": result.get("best_scenario"),
            "ranking": (result.get("ranking") or [])[:3],
        }
    except Exception:
        return {}


def persist_editorial_strategy_snapshot(runtime_dir: str | Path, snapshot: dict[str, Any]) -> dict[str, Any]:
    path = Path(runtime_dir) / "editorial_strategy.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return snapshot


def load_editorial_strategy_snapshot(runtime_dir: str | Path) -> dict[str, Any]:
    path = Path(runtime_dir) / "editorial_strategy.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def editorial_strategy_section(snapshot: dict[str, Any]) -> list[str]:
    lines = ["", "<b>EDITORIAL STRATEGY</b>"]
    if not snapshot or not snapshot.get("portfolio"):
        lines.append("Недостаточно данных для portfolio analysis.")
        return lines

    scorecard = snapshot.get("scorecard") if isinstance(snapshot.get("scorecard"), dict) else {}
    portfolio = snapshot.get("portfolio") or {}
    segments = portfolio.get("segments") or {}
    best = scorecard.get("best_segments") or []
    if best:
        top = best[0]
        roi = (segments.get(top) or {}).get("roi_index")
        lines.append(f"Best ROI segment: <b>{escape(str(top).replace('_', ' ').title())}</b> (index {roi})")

    under = scorecard.get("underinvested_segments") or []
    if under:
        lines.append(f"Underinvested: {escape(', '.join(under))}")
    over = scorecard.get("overinvested_segments") or []
    if over:
        lines.append(f"Overinvested: {escape(', '.join(over))}")

    allocation = snapshot.get("allocation") if isinstance(snapshot.get("allocation"), dict) else {}
    shifts = [
        (seg, data)
        for seg, data in allocation.items()
        if isinstance(data, dict) and abs(float(data.get("delta") or 0)) >= 0.5
    ]
    shifts.sort(key=lambda x: -abs(float(x[1].get("delta") or 0)))
    if shifts:
        lines.append("Recommended allocation shift:")
        for seg, data in shifts[:4]:
            lines.append(
                f"· {escape(seg)}: {data.get('current_share')}% → {data.get('recommended_share')}%"
            )

    impact = snapshot.get("expected_growth_impact") if isinstance(snapshot.get("expected_growth_impact"), dict) else {}
    if impact.get("expected_acquisition_delta") is not None:
        lines.append(
            f"Expected growth impact: <code>{impact.get('expected_acquisition_delta')}</code> "
            f"({escape(str(impact.get('from_segment', '')))} → {escape(str(impact.get('to_segment', '')))})"
        )

    lines.append(f"Strategy score: <code>{scorecard.get('strategy_score')}</code>")
    return lines
