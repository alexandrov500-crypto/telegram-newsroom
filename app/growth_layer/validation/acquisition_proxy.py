"""Acquisition proxy score with stored components for reproducibility."""

from __future__ import annotations

import os
from typing import Any


def acquisition_weights() -> dict[str, float]:
    def _f(name: str, default: float) -> float:
        try:
            return float(os.getenv(name, str(default)))
        except ValueError:
            return default

    return {
        "forward": _f("GROWTH_ACQ_WEIGHT_FORWARD", 2.0),
        "err": _f("GROWTH_ACQ_WEIGHT_ERR", 50.0),
        "engagement": _f("GROWTH_ACQ_WEIGHT_ENGAGEMENT", 10.0),
    }


def compute_acquisition_components(
    *,
    forwards: float,
    err: float,
    engagement: float,
    weights: dict[str, float] | None = None,
) -> dict[str, float]:
    w = weights or acquisition_weights()
    forward_component = round(float(forwards) * w["forward"], 4)
    err_component = round(float(err) * w["err"], 4)
    engagement_component = round(float(engagement) * w["engagement"], 4)
    total = round(forward_component + err_component + engagement_component, 4)
    return {
        "forward_component": forward_component,
        "err_component": err_component,
        "engagement_component": engagement_component,
        "acquisition_proxy_score": total,
    }


def acquisition_proxy_score(row: dict[str, Any]) -> float:
    """Score from stored components, or legacy inline formula."""
    if row.get("forward_component") is not None:
        return round(
            float(row.get("forward_component") or 0)
            + float(row.get("err_component") or 0)
            + float(row.get("engagement_component") or 0),
            4,
        )
    if row.get("acquisition_proxy_score") is not None:
        return float(row["acquisition_proxy_score"])
    forwards = float(row.get("actual_forwards") or 0)
    err = float(row.get("actual_err") or 0)
    engagement = float(row.get("actual_engagement") or 0)
    return compute_acquisition_components(forwards=forwards, err=err, engagement=engagement)[
        "acquisition_proxy_score"
    ]
