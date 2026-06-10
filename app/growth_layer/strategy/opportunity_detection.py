"""Detect under/over-invested content segments."""

from __future__ import annotations

from typing import Any

_UNDERINVESTED_RATIO = 1.25
_OVERINVESTED_RATIO = 1.25
_MIN_POSTS = 3


def _opportunity_score(*, roi_index: float, share_gap: float, kind: str) -> int:
    """Higher score = stronger signal. share_gap = acquisition_share - share_of_content."""
    base = abs(share_gap) * roi_index
    if kind == "UNDERINVESTED":
        base *= 1.0 + max(0.0, roi_index - 1.0)
    else:
        base *= 1.0 + max(0.0, 1.0 - roi_index)
    return max(0, min(100, int(round(base))))


def detect_growth_opportunities(portfolio: dict[str, Any]) -> dict[str, Any]:
    """
    high ROI + low content share vs acquisition share → UNDERINVESTED
    low ROI + high content share vs acquisition share → OVERINVESTED
    """
    segments = portfolio.get("segments") if isinstance(portfolio.get("segments"), dict) else {}
    opportunities: dict[str, Any] = {}

    for segment, data in segments.items():
        if not isinstance(data, dict):
            continue
        if int(data.get("total_posts") or 0) < _MIN_POSTS:
            continue
        share = float(data.get("share_of_content") or 0)
        acq_share = float(data.get("acquisition_share") or 0)
        roi = float(data.get("roi_index") or 1.0)
        gap = acq_share - share

        if roi >= 1.0 and acq_share >= share * _UNDERINVESTED_RATIO and gap > 2.0:
            opportunities[segment] = {
                "type": "UNDERINVESTED",
                "opportunity_score": _opportunity_score(roi_index=roi, share_gap=gap, kind="UNDERINVESTED"),
                "share_of_content": share,
                "acquisition_share": acq_share,
                "roi_index": roi,
                "share_gap": round(gap, 1),
            }
        elif roi <= 1.0 and share >= acq_share * _OVERINVESTED_RATIO and gap < -2.0:
            opportunities[segment] = {
                "type": "OVERINVESTED",
                "opportunity_score": _opportunity_score(roi_index=roi, share_gap=gap, kind="OVERINVESTED"),
                "share_of_content": share,
                "acquisition_share": acq_share,
                "roi_index": roi,
                "share_gap": round(gap, 1),
            }

    return opportunities
