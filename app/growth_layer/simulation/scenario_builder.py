"""Deterministic editorial strategy scenario builder."""

from __future__ import annotations

from typing import Any

_SCENARIO_SHIFT_PCT = 10.0


def _normalize_allocation(allocation: dict[str, float]) -> dict[str, float]:
    total = sum(max(0.0, v) for v in allocation.values())
    if total <= 0:
        n = len(allocation) or 1
        return {k: round(100.0 / n, 1) for k in allocation}
    return {k: round(max(0.0, v) / total * 100.0, 1) for k, v in allocation.items()}


def _extract_current_allocation(base_strategy: dict[str, Any]) -> dict[str, float]:
    allocation_block = base_strategy.get("allocation")
    if isinstance(allocation_block, dict) and allocation_block:
        out: dict[str, float] = {}
        for seg, data in allocation_block.items():
            if isinstance(data, dict):
                out[seg] = float(data.get("current_share") or data.get("recommended_share") or 0)
            else:
                out[seg] = float(data or 0)
        if out:
            return _normalize_allocation(out)

    portfolio = base_strategy.get("portfolio") if isinstance(base_strategy.get("portfolio"), dict) else {}
    segments = portfolio.get("segments") if isinstance(portfolio.get("segments"), dict) else {}
    if segments:
        return _normalize_allocation(
            {seg: float((data or {}).get("share_of_content") or 0) for seg, data in segments.items()}
        )
    return {}


def _shift_allocation(
    current: dict[str, float],
    *,
    boost: str | None = None,
    cut: str | None = None,
    shift_pct: float = _SCENARIO_SHIFT_PCT,
) -> dict[str, float]:
    if not current:
        return {}
    result = dict(current)
    delta = min(shift_pct, 100.0)
    if boost and boost in result:
        result[boost] = result.get(boost, 0.0) + delta
    if cut and cut in result:
        result[cut] = max(0.0, result.get(cut, 0.0) - delta)
    if boost and boost in result and not cut:
        donors = sorted(
            (s for s in result if s != boost),
            key=lambda s: result[s],
            reverse=True,
        )
        remaining = delta
        for donor in donors:
            if remaining <= 0:
                break
            take = min(remaining, result[donor])
            result[donor] -= take
            remaining -= take
    elif cut and cut in result and not boost:
        receivers = sorted(
            (s for s in result if s != cut),
            key=lambda s: result[s],
        )
        remaining = delta
        for receiver in receivers:
            if remaining <= 0:
                break
            result[receiver] += remaining / max(len(receivers), 1)
            remaining = 0
    return _normalize_allocation(result)


def _balanced_allocation(current: dict[str, float]) -> dict[str, float]:
    if not current:
        return {}
    n = len(current)
    equal = round(100.0 / n, 1)
    out = {k: equal for k in current}
    drift = 100.0 - sum(out.values())
    if out:
        first = next(iter(out))
        out[first] = round(out[first] + drift, 1)
    return out


def _aggressive_allocation(current: dict[str, float], portfolio: dict[str, Any]) -> dict[str, float]:
    segments = portfolio.get("segments") if isinstance(portfolio.get("segments"), dict) else {}
    if not segments or not current:
        return dict(current)
    ranked = sorted(
        segments.items(),
        key=lambda kv: float((kv[1] or {}).get("roi_index") or 0),
        reverse=True,
    )
    best = ranked[0][0] if ranked else None
    worst = ranked[-1][0] if ranked else None
    if best and worst and best != worst:
        return _shift_allocation(current, boost=best, cut=worst, shift_pct=_SCENARIO_SHIFT_PCT)
    return dict(current)


def _conservative_allocation(current: dict[str, float]) -> dict[str, float]:
    """Minimal change: blend 80% current + 20% balanced."""
    if not current:
        return {}
    balanced = _balanced_allocation(current)
    blended = {
        seg: round(current.get(seg, 0.0) * 0.8 + balanced.get(seg, 0.0) * 0.2, 1)
        for seg in current
    }
    return _normalize_allocation(blended)


def extract_current_allocation(base_strategy: dict[str, Any]) -> dict[str, float]:
    """Public helper: current segment share map from strategy snapshot."""
    return _extract_current_allocation(base_strategy)


def build_strategy_scenarios(base_strategy: dict[str, Any]) -> dict[str, Any]:
    """
    Generate deterministic what-if scenarios from current editorial strategy.
    """
    current = _extract_current_allocation(base_strategy)
    portfolio = base_strategy.get("portfolio") if isinstance(base_strategy.get("portfolio"), dict) else {}
    if not current:
        return {"scenarios": [], "base_allocation": {}}

    segments = list(current.keys())
    tech = "technology" if "technology" in current else segments[0]
    markets = "markets" if "markets" in current else (segments[1] if len(segments) > 1 else segments[0])

    scenarios: list[dict[str, Any]] = [
        {
            "name": "tech_boost",
            "label": "Technology +10%",
            "allocation": _shift_allocation(current, boost=tech, shift_pct=_SCENARIO_SHIFT_PCT),
        },
        {
            "name": "markets_cut",
            "label": "Markets -10%",
            "allocation": _shift_allocation(current, cut=markets, shift_pct=_SCENARIO_SHIFT_PCT),
        },
        {
            "name": "balanced",
            "label": "Balanced distribution",
            "allocation": _balanced_allocation(current),
        },
        {
            "name": "aggressive_growth",
            "label": "Aggressive growth mode",
            "allocation": _aggressive_allocation(current, portfolio),
        },
        {
            "name": "conservative",
            "label": "Conservative mode",
            "allocation": _conservative_allocation(current),
        },
    ]

    return {
        "base_allocation": current,
        "scenarios": scenarios,
    }
