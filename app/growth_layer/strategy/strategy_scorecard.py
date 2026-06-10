"""Editorial strategy scorecard."""

from __future__ import annotations

from typing import Any


def build_strategy_scorecard(
    portfolio: dict[str, Any],
    opportunities: dict[str, Any] | None = None,
    allocation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Portfolio-level strategy health and segment lists."""
    segments = portfolio.get("segments") if isinstance(portfolio.get("segments"), dict) else {}
    opps = opportunities or {}

    ranked = sorted(
        segments.items(),
        key=lambda kv: float((kv[1] or {}).get("roi_index") or 0),
        reverse=True,
    )
    best_segments = [seg for seg, _ in ranked[:3] if segments.get(seg)]
    underinvested = [s for s, o in opps.items() if o.get("type") == "UNDERINVESTED"]
    overinvested = [s for s, o in opps.items() if o.get("type") == "OVERINVESTED"]

    # Balance score: penalize large share/ROI mismatches
    mismatch_penalty = 0.0
    for data in segments.values():
        if not isinstance(data, dict):
            continue
        share = float(data.get("share_of_content") or 0)
        acq = float(data.get("acquisition_share") or 0)
        mismatch_penalty += abs(share - acq)
    balance = max(0.0, 100.0 - mismatch_penalty * 1.5)

    roi_vals = [float(d.get("roi_index") or 1.0) for d in segments.values() if isinstance(d, dict)]
    roi_spread = (max(roi_vals) - min(roi_vals)) if len(roi_vals) >= 2 else 0.0
    diversification = max(0.0, 100.0 - roi_spread * 30.0)

    strategy_score = max(0, min(100, int(round(balance * 0.6 + diversification * 0.4))))

    total_positive_shift = 0.0
    if allocation:
        total_positive_shift = sum(
            max(0.0, float(v.get("delta") or 0)) for v in allocation.values() if isinstance(v, dict)
        )

    return {
        "strategy_score": strategy_score,
        "best_segments": best_segments,
        "underinvested_segments": underinvested,
        "overinvested_segments": overinvested,
        "portfolio_balance_score": round(balance, 1),
        "diversification_score": round(diversification, 1),
        "recommended_reallocation_magnitude": round(total_positive_shift, 1),
    }
