"""Simulation reporting, snapshots, and integrations."""

from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any

from app.growth_layer.simulation.impact_estimator import estimate_strategy_impact
from app.growth_layer.simulation.scenario_builder import build_strategy_scenarios, extract_current_allocation
from app.growth_layer.simulation.strategy_simulator import simulate_strategy


def simulate_top_scenarios(strategy_snapshot: dict[str, Any]) -> dict[str, Any]:
    """
    Phase 4A hook: run sandbox simulations for top strategy scenarios.
    """
    portfolio = strategy_snapshot.get("portfolio") if isinstance(strategy_snapshot.get("portfolio"), dict) else {}
    if not portfolio.get("segments"):
        return {"best_scenario": None, "ranking": [], "scenarios": []}

    base_strategy = {
        "portfolio": portfolio,
        "allocation": strategy_snapshot.get("allocation"),
    }
    scenarios = build_strategy_scenarios(base_strategy)
    comparison = simulate_strategy(base_strategy, scenarios, portfolio)
    return {
        **comparison,
        "scenarios": scenarios.get("scenarios") or [],
    }


def build_editorial_simulation_snapshot(
    strategy_snapshot: dict[str, Any] | None = None,
    *,
    rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build full Phase 4C simulation snapshot."""
    if strategy_snapshot is None and rows is not None:
        from app.growth_layer.strategy.strategy_reporting import build_editorial_strategy_snapshot

        strategy_snapshot = build_editorial_strategy_snapshot(rows)

    strategy_snapshot = strategy_snapshot or {}
    simulation = simulate_top_scenarios(strategy_snapshot)
    portfolio = strategy_snapshot.get("portfolio") or {}

    best_name = simulation.get("best_scenario")
    best_projection = next(
        (r for r in (simulation.get("projections") or []) if r.get("scenario") == best_name),
        {},
    )
    best_impact = estimate_strategy_impact(
        {"name": best_name, "allocation": best_projection.get("allocation") or {}},
        portfolio,
        base_allocation=simulation.get("base_allocation"),
    )

    risk_scores = [float(r.get("risk_score") or 0) for r in (simulation.get("projections") or [])]
    avg_risk = round(sum(risk_scores) / len(risk_scores), 2) if risk_scores else 0.0

    segments = portfolio.get("segments") if isinstance(portfolio.get("segments"), dict) else {}
    top_roi_seg = None
    top_roi = 0.0
    for seg, data in segments.items():
        roi = float((data or {}).get("roi_index") or 0)
        if roi > top_roi:
            top_roi = roi
            top_roi_seg = seg

    return {
        "best_scenario": best_name,
        "ranking": simulation.get("ranking") or [],
        "projections": simulation.get("projections") or [],
        "base_allocation": simulation.get("base_allocation") or extract_current_allocation(strategy_snapshot),
        "risk_assessment": {
            "average_risk_score": avg_risk,
            "best_scenario_risk": best_projection.get("risk_score"),
            "risk_label": best_impact.get("risk"),
        },
        "best_scenario_impact": best_impact,
        "key_driver": {
            "segment": top_roi_seg,
            "roi_index": top_roi,
        },
        "scenario_reports": [
            format_scenario_report(r, portfolio=portfolio) for r in (simulation.get("projections") or [])[:3]
        ],
    }


def format_scenario_report(projection: dict[str, Any], *, portfolio: dict[str, Any] | None = None) -> str:
    """Human-readable scenario block."""
    name = str(projection.get("label") or projection.get("scenario") or "SCENARIO").upper()
    acq = float(projection.get("expected_acquisition_delta") or 0)
    err = float(projection.get("expected_err_change") or 0)
    risk_score = float(projection.get("risk_score") or 0)
    risk = "LOW" if risk_score <= 0.25 else ("MEDIUM" if risk_score <= 0.55 else "HIGH")

    lines = [
        f"SCENARIO: {name}",
        f"Expected acquisition: {acq:+.0%}" if abs(acq) <= 1 else f"Expected acquisition: {acq:+.2f}",
        f"Expected ERR: {err:+.0%}" if abs(err) <= 1 else f"Expected ERR: {err:+.4f}",
        f"Risk: {risk}",
    ]

    pf = portfolio or {}
    segments = pf.get("segments") if isinstance(pf.get("segments"), dict) else {}
    if segments:
        best = max(segments.items(), key=lambda kv: float((kv[1] or {}).get("roi_index") or 0))
        lines.append(f"KEY DRIVER:\n{best[0].replace('_', ' ').title()} ROI = {best[1].get('roi_index')} (highest in system)")

    return "\n".join(lines)


def persist_editorial_simulation_snapshot(runtime_dir: str | Path, snapshot: dict[str, Any]) -> dict[str, Any]:
    path = Path(runtime_dir) / "editorial_simulation.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return snapshot


def load_editorial_simulation_snapshot(runtime_dir: str | Path) -> dict[str, Any]:
    path = Path(runtime_dir) / "editorial_simulation.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def editorial_simulation_section(snapshot: dict[str, Any]) -> list[str]:
    lines = ["", "<b>EDITORIAL SIMULATION</b>"]
    if not snapshot or not snapshot.get("ranking"):
        lines.append("Недостаточно данных для what-if simulation.")
        return lines

    best = snapshot.get("best_scenario")
    impact = snapshot.get("best_scenario_impact") if isinstance(snapshot.get("best_scenario_impact"), dict) else {}
    risk = snapshot.get("risk_assessment") if isinstance(snapshot.get("risk_assessment"), dict) else {}
    driver = snapshot.get("key_driver") if isinstance(snapshot.get("key_driver"), dict) else {}

    lines.append(f"Best scenario: <b>{escape(str(best or 'n/a').replace('_', ' ').title())}</b>")
    if impact.get("acquisition_gain") is not None:
        lines.append(f"Expected acquisition: <code>{impact.get('acquisition_gain')}</code>")
    if impact.get("expected_err_change") is not None:
        lines.append(f"Expected ERR: <code>{impact.get('expected_err_change')}</code>")
    lines.append(f"Risk: <code>{escape(str(risk.get('risk_label') or impact.get('risk') or 'n/a'))}</code>")

    ranking = snapshot.get("ranking") if isinstance(snapshot.get("ranking"), list) else []
    if ranking:
        lines.append("Scenario ranking:")
        for item in ranking[:4]:
            if not isinstance(item, dict):
                continue
            lines.append(
                f"· {escape(str(item.get('scenario', '')))}: impact "
                f"<code>{item.get('impact')}</code> risk <code>{item.get('risk_score')}</code>"
            )

    if driver.get("segment"):
        lines.append(
            f"Key driver: {escape(str(driver['segment']).replace('_', ' ').title())} "
            f"(ROI {driver.get('roi_index')})"
        )
    return lines


def check_scenario_alignment(
    simulation_snapshot: dict[str, Any],
    control_recommendation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Phase 4B hook: verify control-layer action aligns with best simulated scenario.
    """
    best = simulation_snapshot.get("best_scenario")
    if not best:
        return {"aligned": True, "reason": "no_simulation_data", "best_scenario": None}

    rec = control_recommendation or {}
    proposed = str(rec.get("scenario") or rec.get("strategy") or rec.get("recommended_scenario") or "")
    proposed_segment = str(rec.get("segment") or rec.get("target_segment") or "")

    aligned = False
    reason = "mismatch"
    if proposed and proposed == best:
        aligned = True
        reason = "exact_scenario_match"
    elif proposed_segment:
        best_proj = next(
            (r for r in (simulation_snapshot.get("projections") or []) if r.get("scenario") == best),
            {},
        )
        delta = (best_proj.get("allocation_delta") or {}) if isinstance(best_proj, dict) else {}
        if float(delta.get(proposed_segment, 0)) > 0:
            aligned = True
            reason = "segment_boost_aligned"
    elif not proposed and not proposed_segment:
        aligned = True
        reason = "no_control_action_pending"

    return {
        "aligned": aligned,
        "best_scenario": best,
        "proposed_scenario": proposed or None,
        "proposed_segment": proposed_segment or None,
        "reason": reason,
        "confidence": (simulation_snapshot.get("best_scenario_impact") or {}).get("confidence"),
    }
