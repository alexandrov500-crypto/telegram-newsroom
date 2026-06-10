"""Linear growth budget simulation (no ML)."""

from __future__ import annotations

from typing import Any


def simulate_growth_budget_shift(
    portfolio: dict[str, Any],
    *,
    from_segment: str,
    to_segment: str,
    delta_percent: float,
) -> dict[str, Any]:
    """
    Project expected acquisition impact from shifting content share.
    Linear projection based on historical segment ROI (acquisition_proxy_score).
    """
    segments = portfolio.get("segments") if isinstance(portfolio.get("segments"), dict) else {}
    global_block = portfolio.get("global") if isinstance(portfolio.get("global"), dict) else {}
    src = segments.get(from_segment) or {}
    dst = segments.get(to_segment) or {}

    if not src or not dst:
        return {
            "from_segment": from_segment,
            "to_segment": to_segment,
            "delta_percent": delta_percent,
            "expected_acquisition_delta": 0.0,
            "explainable": False,
            "reason": "unknown_segment",
        }

    src_acq = float(src.get("acquisition_proxy_score") or 0)
    dst_acq = float(dst.get("acquisition_proxy_score") or 0)
    global_acq = float(global_block.get("acquisition_proxy_score") or 1.0)
    total_posts = int(portfolio.get("total_posts") or 0)

    # Shift delta_percent of portfolio from source to destination
    shift_fraction = max(0.0, min(100.0, float(delta_percent))) / 100.0
    posts_shifted = total_posts * shift_fraction
    acq_gain_per_post = dst_acq - src_acq
    expected_delta = round((posts_shifted * acq_gain_per_post) / max(total_posts, 1) / max(global_acq, 1e-9), 4)

    return {
        "from_segment": from_segment,
        "to_segment": to_segment,
        "delta_percent": round(float(delta_percent), 1),
        "expected_acquisition_delta": expected_delta,
        "expected_err_lift_proxy": round((float(dst.get("avg_err") or 0) - float(src.get("avg_err") or 0)) * shift_fraction, 4),
        "source_roi_index": src.get("roi_index"),
        "destination_roi_index": dst.get("roi_index"),
        "explainable": True,
        "method": "linear_acquisition_proxy_projection",
    }
