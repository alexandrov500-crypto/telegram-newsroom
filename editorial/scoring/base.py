"""Shared scoring helpers."""

from __future__ import annotations

from typing import Any


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def level_label(score: float, *, high: float = 0.72, medium: float = 0.45) -> str:
    if score >= high:
        return "high"
    if score >= medium:
        return "medium"
    return "low"


def mean_or(default: float, values: list[float]) -> float:
    if not values:
        return default
    return sum(values) / len(values)


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
