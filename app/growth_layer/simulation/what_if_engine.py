"""Deterministic what-if projection engine (no ML)."""

from __future__ import annotations

from typing import Any


def _segment_metrics(portfolio: dict[str, Any]) -> dict[str, dict[str, float]]:
    segments = portfolio.get("segments") if isinstance(portfolio.get("segments"), dict) else {}
    out: dict[str, dict[str, float]] = {}
    for seg, data in segments.items():
        if not isinstance(data, dict):
            continue
        out[seg] = {
            "acquisition_proxy_score": float(data.get("acquisition_proxy_score") or 0),
            "avg_err": float(data.get("avg_err") or 0),
            "roi_index": float(data.get("roi_index") or 1.0),
            "share_of_content": float(data.get("share_of_content") or 0),
        }
    return out


def _engagement_multiplier(roi_index: float) -> float:
    """Historical engagement lift proxy from ROI index (deterministic)."""
    return round(1.0 + max(0.0, roi_index - 1.0) * 0.15, 4)


def _risk_score(
    *,
    allocation_delta: dict[str, float],
    segment_metrics: dict[str, dict[str, float]],
) -> float:
    total_shift = sum(abs(v) for v in allocation_delta.values())
    concentration = 0.0
    for seg, delta in allocation_delta.items():
        if abs(delta) < 0.5:
            continue
        roi = segment_metrics.get(seg, {}).get("roi_index", 1.0)
        if delta > 0 and roi < 1.0:
            concentration += abs(delta) * (1.0 - roi)
        elif delta < 0 and roi > 1.0:
            concentration += abs(delta) * (roi - 1.0)
    raw = total_shift / 200.0 + concentration / 100.0
    return round(min(1.0, max(0.0, raw)), 2)


def run_what_if_simulation(
    scenario: dict[str, Any],
    portfolio: dict[str, Any],
    *,
    base_allocation: dict[str, float] | None = None,
) -> dict[str, Any]:
    """
    Project acquisition / ERR impact for a single scenario.
    Weighted historical averages only — reproducible, explainable.
    """
    scenario_name = str(scenario.get("name") or "unknown")
    target = scenario.get("allocation") if isinstance(scenario.get("allocation"), dict) else {}
    if not target:
        return {
            "scenario": scenario_name,
            "expected_acquisition_delta": 0.0,
            "expected_err_change": 0.0,
            "risk_score": 0.0,
            "explainable": False,
        }

    metrics = _segment_metrics(portfolio)
    global_block = portfolio.get("global") if isinstance(portfolio.get("global"), dict) else {}
    global_acq = float(global_block.get("acquisition_proxy_score") or 1.0)
    global_err = float(global_block.get("avg_err") or 0)

    if base_allocation is None:
        base_allocation = {
            seg: float(m.get("share_of_content") or 0) for seg, m in metrics.items()
        }

    all_segments = set(base_allocation) | set(target)
    acq_delta = 0.0
    err_delta = 0.0
    allocation_delta: dict[str, float] = {}

    for seg in all_segments:
        old_share = float(base_allocation.get(seg, 0)) / 100.0
        new_share = float(target.get(seg, base_allocation.get(seg, 0))) / 100.0
        share_delta = new_share - old_share
        allocation_delta[seg] = round(share_delta * 100.0, 1)
        if abs(share_delta) < 1e-9:
            continue
        seg_acq = metrics.get(seg, {}).get("acquisition_proxy_score", global_acq)
        seg_err = metrics.get(seg, {}).get("avg_err", global_err)
        roi = metrics.get(seg, {}).get("roi_index", 1.0)
        eng_mult = _engagement_multiplier(roi)
        acq_delta += share_delta * (seg_acq / max(global_acq, 1e-9)) * eng_mult
        err_delta += share_delta * (seg_err - global_err)

    return {
        "scenario": scenario_name,
        "label": scenario.get("label"),
        "allocation": target,
        "expected_acquisition_delta": round(acq_delta, 4),
        "expected_err_change": round(err_delta, 4),
        "risk_score": _risk_score(allocation_delta=allocation_delta, segment_metrics=metrics),
        "allocation_delta": allocation_delta,
        "method": "weighted_historical_average",
        "explainable": True,
    }
