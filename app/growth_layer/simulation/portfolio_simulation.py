"""Portfolio shift simulation between two allocation strategies."""

from __future__ import annotations

from typing import Any

from app.growth_layer.simulation.what_if_engine import run_what_if_simulation


def _normalize_shares(shares: dict[str, float]) -> dict[str, float]:
    total = sum(max(0.0, v) for v in shares.values())
    if total <= 0:
        n = len(shares) or 1
        return {k: round(100.0 / n, 1) for k in shares}
    return {k: round(max(0.0, v) / total * 100.0, 1) for k, v in shares.items()}


def _segment_pressure_delta(
    *,
    from_alloc: dict[str, float],
    to_alloc: dict[str, float],
    portfolio: dict[str, Any],
) -> dict[str, float]:
    """Positive = increased editorial pressure on segment."""
    segments = portfolio.get("segments") if isinstance(portfolio.get("segments"), dict) else {}
    pressure: dict[str, float] = {}
    all_segs = set(from_alloc) | set(to_alloc)
    for seg in all_segs:
        delta = float(to_alloc.get(seg, 0)) - float(from_alloc.get(seg, 0))
        roi = float((segments.get(seg) or {}).get("roi_index") or 1.0)
        pressure[seg] = round(delta * roi, 2)
    return pressure


def simulate_portfolio_shift(
    from_strategy: dict[str, float],
    to_strategy: dict[str, float],
    portfolio: dict[str, Any],
) -> dict[str, Any]:
    """
    Compare two allocation strategies: acquisition delta, ERR delta, segment pressure.
    """
    from_alloc = _normalize_shares({k: float(v) for k, v in from_strategy.items()})
    to_alloc = _normalize_shares({k: float(v) for k, v in to_strategy.items()})

    projection = run_what_if_simulation(
        {"name": "portfolio_shift", "allocation": to_alloc},
        portfolio,
        base_allocation=from_alloc,
    )

    pressure = _segment_pressure_delta(from_alloc=from_alloc, to_alloc=to_alloc, portfolio=portfolio)
    increased = sorted(
        ((s, p) for s, p in pressure.items() if p > 0.5),
        key=lambda x: -x[1],
    )
    decreased = sorted(
        ((s, p) for s, p in pressure.items() if p < -0.5),
        key=lambda x: x[1],
    )

    return {
        "from_allocation": from_alloc,
        "to_allocation": to_alloc,
        "expected_acquisition_delta": projection.get("expected_acquisition_delta"),
        "expected_err_change": projection.get("expected_err_change"),
        "risk_score": projection.get("risk_score"),
        "segment_pressure_change": pressure,
        "pressure_increased": [s for s, _ in increased[:3]],
        "pressure_decreased": [s for s, _ in decreased[:3]],
        "method": "deterministic_portfolio_shift",
    }
