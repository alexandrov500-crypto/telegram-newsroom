"""Aggregate language / structure quality from existing heuristic signals."""

from __future__ import annotations

from typing import Any

from editorial.scoring.base import (
    WEIGHT_QUALITY_COHERENCE,
    WEIGHT_QUALITY_FACTUAL,
    WEIGHT_QUALITY_LENGTH,
    WEIGHT_QUALITY_NON_REPETITION,
    WEIGHT_QUALITY_SOURCE_COVERAGE,
    normalize_score,
    safe_float,
)


def compute_quality_score(quality_scores: dict[str, Any] | None) -> float:
    q = quality_scores or {}
    return normalize_score(
        WEIGHT_QUALITY_COHERENCE * safe_float(q.get("coherence"), 0.5)
        + WEIGHT_QUALITY_LENGTH * safe_float(q.get("length_quality"), 0.5)
        + WEIGHT_QUALITY_SOURCE_COVERAGE * safe_float(q.get("source_coverage"), 0.5)
        + WEIGHT_QUALITY_FACTUAL * safe_float(q.get("factual_confidence_heuristic"), 0.5)
        + WEIGHT_QUALITY_NON_REPETITION * (1.0 - safe_float(q.get("repetition"), 0.0))
    )
