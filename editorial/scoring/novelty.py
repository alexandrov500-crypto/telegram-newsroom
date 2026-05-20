"""Semantic novelty from duplicate intel and repetition heuristics."""

from __future__ import annotations

from typing import Any

from editorial.scoring.base import clamp01, safe_float


def compute_novelty_score(
    *,
    quality_scores: dict[str, Any] | None,
    duplicate_intel: dict[str, Any] | None,
) -> float:
    q = quality_scores or {}
    intel = duplicate_intel or {}
    repetition = safe_float(q.get("repetition"), 0.0)
    max_pct = safe_float(intel.get("max_similarity_pct"), 0.0)
    dup_penalty = max_pct / 100.0
    base = 1.0 - 0.55 * dup_penalty - 0.35 * repetition
    related = intel.get("related") if isinstance(intel.get("related"), list) else []
    if len(related) >= 3:
        base -= 0.08
    return round(clamp01(base), 4)
