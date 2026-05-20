"""Operator feedback hook (nullable until Phase 2.2+ adaptive ranking)."""

from __future__ import annotations

from dataclasses import replace

from editorial.scoring.base import normalize_score
from editorial.scoring.models import EditorialIntelligenceScores


def apply_operator_feedback(
    scores: EditorialIntelligenceScores,
    *,
    operator_feedback_score: float | None = None,
    operator_feedback_label: str | None = None,
) -> EditorialIntelligenceScores:
    """
    Attach operator feedback without recomputing heuristics.
    ``operator_feedback_score`` is normalized to ``[0, 1]`` when set.
    """
    if operator_feedback_score is None and operator_feedback_label is None:
        return scores
    norm_score = (
        normalize_score(operator_feedback_score) if operator_feedback_score is not None else None
    )
    return replace(
        scores,
        operator_feedback_score=norm_score,
        operator_feedback_label=(str(operator_feedback_label).strip()[:64] or None),
    )
