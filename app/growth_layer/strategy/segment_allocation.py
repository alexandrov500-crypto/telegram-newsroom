"""Recommend editorial content allocation shifts."""

from __future__ import annotations

from typing import Any

_MAX_SHIFT_PCT = 10.0


def _normalize_shares(shares: dict[str, float]) -> dict[str, float]:
    total = sum(shares.values())
    if total <= 0:
        n = len(shares) or 1
        return {k: round(100.0 / n, 1) for k in shares}
    return {k: round(v / total * 100.0, 1) for k, v in shares.items()}


def recommend_content_allocation(
    portfolio: dict[str, Any],
    opportunities: dict[str, Any] | None = None,
    *,
    max_shift_pct: float = _MAX_SHIFT_PCT,
) -> dict[str, Any]:
    """
    Propose bounded allocation shifts (±max_shift_pct per segment per cycle).
    Sum of recommended shares = 100%.
    """
    segments = portfolio.get("segments") if isinstance(portfolio.get("segments"), dict) else {}
    if not segments:
        return {}

    opps = opportunities or {}
    current = {seg: float(data.get("share_of_content") or 0) for seg, data in segments.items()}
    recommended = dict(current)

    for segment, opp in opps.items():
        if segment not in recommended:
            continue
        if not isinstance(opp, dict):
            continue
        kind = str(opp.get("type") or "")
        score = int(opp.get("opportunity_score") or 0)
        shift = min(max_shift_pct, max(1.0, score / 10.0))
        if kind == "UNDERINVESTED":
            recommended[segment] = min(100.0, recommended[segment] + shift)
        elif kind == "OVERINVESTED":
            recommended[segment] = max(0.0, recommended[segment] - shift)

    # Rebalance: take from overinvested / give to underinvested proportionally
    delta = sum(recommended.values()) - 100.0
    if abs(delta) > 0.01:
        donors = [s for s, o in opps.items() if o.get("type") == "OVERINVESTED" and s in recommended]
        receivers = [s for s, o in opps.items() if o.get("type") == "UNDERINVESTED" and s in recommended]
        if not donors:
            donors = sorted(recommended.keys(), key=lambda s: recommended[s], reverse=True)
        if not receivers:
            receivers = sorted(recommended.keys(), key=lambda s: recommended[s])
        if delta > 0 and donors:
            per = delta / len(donors)
            for s in donors:
                recommended[s] = max(0.0, recommended[s] - per)
        elif delta < 0 and receivers:
            per = abs(delta) / len(receivers)
            for s in receivers:
                recommended[s] += per

    recommended = _normalize_shares(recommended)

    # Enforce per-segment bounded change from current
    for segment in list(recommended.keys()):
        cur = current.get(segment, 0.0)
        rec = recommended[segment]
        if rec > cur + max_shift_pct:
            recommended[segment] = round(cur + max_shift_pct, 1)
        elif rec < cur - max_shift_pct:
            recommended[segment] = round(max(0.0, cur - max_shift_pct), 1)

    recommended = _normalize_shares(recommended)

    out: dict[str, Any] = {}
    for segment in segments:
        cur = round(current.get(segment, 0.0), 1)
        rec = recommended.get(segment, cur)
        out[segment] = {
            "current_share": cur,
            "recommended_share": rec,
            "delta": round(rec - cur, 1),
        }
    return out
