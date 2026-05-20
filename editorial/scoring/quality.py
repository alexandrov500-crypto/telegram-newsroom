"""Aggregate language / structure quality from existing heuristic signals."""

from __future__ import annotations

from typing import Any

from editorial.scoring.base import clamp01, safe_float


def compute_quality_score(quality_scores: dict[str, Any] | None) -> float:
    q = quality_scores or {}
    parts = [
        safe_float(q.get("coherence"), 0.5),
        safe_float(q.get("length_quality"), 0.5),
        safe_float(q.get("source_coverage"), 0.5),
        safe_float(q.get("factual_confidence_heuristic"), 0.5),
        1.0 - safe_float(q.get("repetition"), 0.0),
    ]
    return round(clamp01(sum(parts) / len(parts)), 4)
