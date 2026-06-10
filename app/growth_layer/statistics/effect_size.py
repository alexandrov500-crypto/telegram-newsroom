"""Cohen's d effect size and classification."""

from __future__ import annotations

import math
from typing import Any


def classify_effect_size(d: float | None) -> str:
    if d is None:
        return "unknown"
    ad = abs(float(d))
    if ad < 0.2:
        return "negligible"
    if ad < 0.5:
        return "small"
    if ad < 0.8:
        return "medium"
    return "large"


def calculate_effect_size(sample_a: list[float], sample_b: list[float]) -> dict[str, Any]:
    """
    Cohen's d for independent samples (a - b).
    Positive d means sample_a has higher mean than sample_b.
    """
    if len(sample_a) < 2 or len(sample_b) < 2:
        return {"value": None, "classification": "unknown"}

    mean_a = sum(sample_a) / len(sample_a)
    mean_b = sum(sample_b) / len(sample_b)
    var_a = sum((x - mean_a) ** 2 for x in sample_a) / (len(sample_a) - 1)
    var_b = sum((x - mean_b) ** 2 for x in sample_b) / (len(sample_b) - 1)
    pooled = math.sqrt(((len(sample_a) - 1) * var_a + (len(sample_b) - 1) * var_b) / (len(sample_a) + len(sample_b) - 2))
    if pooled <= 1e-12:
        value = 0.0 if abs(mean_a - mean_b) < 1e-12 else float("inf")
        if math.isinf(value):
            value = 99.0
    else:
        value = (mean_a - mean_b) / pooled
    value = round(float(value), 4)
    return {"value": value, "classification": classify_effect_size(value)}


def effect_size_meets_minimum(classification: str, *, minimum: str = "small") -> bool:
    order = {"negligible": 0, "unknown": -1, "small": 1, "medium": 2, "large": 3}
    return order.get(classification, -1) >= order.get(minimum, 1)
