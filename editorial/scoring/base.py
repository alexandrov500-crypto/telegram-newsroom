"""Shared scoring helpers and Phase 2.1 contracts.

Score invariants (all dimension scores):
- Range: ``0.0 .. 1.0`` inclusive
- ``0.0`` = worst / none / lowest confidence
- ``1.0`` = strongest / highest confidence

``duplicate_confidence`` follows the same range where higher = more duplicate risk.
"""

from __future__ import annotations

from typing import Any

SCORING_VERSION = "phase2.1-v1"

SCORE_MIN = 0.0
SCORE_MAX = 1.0

# Publish priority label derived deterministically from ``publish_priority_score``.
PRIORITY_HIGH_THRESHOLD = 0.72
PRIORITY_MEDIUM_THRESHOLD = 0.45

# Composable heuristic weights (sum ≈ 1.0 per composite where applicable).
WEIGHT_QUALITY_COHERENCE = 0.25
WEIGHT_QUALITY_LENGTH = 0.20
WEIGHT_QUALITY_SOURCE_COVERAGE = 0.20
WEIGHT_QUALITY_FACTUAL = 0.20
WEIGHT_QUALITY_NON_REPETITION = 0.15

WEIGHT_CLUSTER_SIZE = 0.45
WEIGHT_CLUSTER_CHANNELS = 0.35
WEIGHT_CLUSTER_CONVERGENCE = 0.20


def clamp01(value: float) -> float:
    return max(SCORE_MIN, min(SCORE_MAX, float(value)))


def normalize_score(value: Any, *, default: float = 0.0) -> float:
    """Coerce to float and clamp to ``[0.0, 1.0]``."""
    try:
        return round(clamp01(float(value)), 4)
    except (TypeError, ValueError):
        return round(clamp01(default), 4)


def level_label(
    score: float,
    *,
    high: float = PRIORITY_HIGH_THRESHOLD,
    medium: float = PRIORITY_MEDIUM_THRESHOLD,
) -> str:
    s = normalize_score(score)
    if s >= high:
        return "high"
    if s >= medium:
        return "medium"
    return "low"


def publish_priority_label(publish_priority_score: float) -> str:
    """Deterministic HIGH / MEDIUM / LOW from normalized publish priority score."""
    s = normalize_score(publish_priority_score)
    if s >= PRIORITY_HIGH_THRESHOLD:
        return "HIGH"
    if s >= PRIORITY_MEDIUM_THRESHOLD:
        return "MEDIUM"
    return "LOW"


def mean_or(default: float, values: list[float]) -> float:
    if not values:
        return normalize_score(default)
    return normalize_score(sum(values) / len(values))


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
