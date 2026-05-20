"""Typed editorial intelligence scores (Phase 2.1 — explainable heuristics)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from typing import Any

from editorial.scoring.base import SCORING_VERSION, normalize_score, publish_priority_label


@dataclass(slots=True)
class ScoringInput:
    """Inputs gathered after draft creation (deterministic, no ML)."""

    draft_id: int
    draft_text: str
    cluster_size: int
    source_count: int
    unique_channel_count: int
    quality_scores: dict[str, Any]
    duplicate_intel: dict[str, Any]
    editorial_scores_card: dict[str, float]
    publication_priority: dict[str, Any] | None
    editorial_priority: dict[str, Any] | None
    source_trust_by_channel: dict[str, float]
    source_convergence: float = 0.0


@dataclass(slots=True)
class EditorialIntelligenceScores:
    quality_score: float
    novelty_score: float
    source_trust_score: float
    duplicate_confidence: float
    cluster_importance_score: float
    publish_priority_score: float
    operator_feedback_score: float | None = None
    operator_feedback_label: str | None = None
    publish_priority_label: str = "MEDIUM"
    scoring_version: str = SCORING_VERSION
    reason_codes: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def normalized(self) -> EditorialIntelligenceScores:
        """Enforce ``[0, 1]`` contract on all dimension scores."""
        return replace(
            self,
            quality_score=normalize_score(self.quality_score),
            novelty_score=normalize_score(self.novelty_score),
            source_trust_score=normalize_score(self.source_trust_score),
            duplicate_confidence=normalize_score(self.duplicate_confidence),
            cluster_importance_score=normalize_score(self.cluster_importance_score),
            publish_priority_score=normalize_score(self.publish_priority_score),
            operator_feedback_score=(
                normalize_score(self.operator_feedback_score)
                if self.operator_feedback_score is not None
                else None
            ),
            publish_priority_label=publish_priority_label(self.publish_priority_score),
            scoring_version=SCORING_VERSION,
        )

    def to_extras_payload(self) -> dict[str, Any]:
        n = self.normalized()
        return {
            "scoring_version": n.scoring_version,
            "quality_score": n.quality_score,
            "novelty_score": n.novelty_score,
            "source_trust_score": n.source_trust_score,
            "duplicate_confidence": n.duplicate_confidence,
            "cluster_importance_score": n.cluster_importance_score,
            "publish_priority_score": n.publish_priority_score,
            "publish_priority": n.publish_priority_label,
            "operator_feedback_score": n.operator_feedback_score,
            "operator_feedback_label": n.operator_feedback_label,
            "reason_codes": list(n.reason_codes),
            "reasons": list(n.reasons),
        }

    def to_db_row(self, *, draft_id: int) -> dict[str, Any]:
        n = self.normalized()
        return {
            "draft_id": draft_id,
            "scoring_version": n.scoring_version,
            "quality_score": n.quality_score,
            "novelty_score": n.novelty_score,
            "source_trust_score": n.source_trust_score,
            "duplicate_confidence": n.duplicate_confidence,
            "cluster_importance_score": n.cluster_importance_score,
            "publish_priority_score": n.publish_priority_score,
            "operator_feedback_score": n.operator_feedback_score,
            "operator_feedback_label": n.operator_feedback_label,
            "reasons_json": json.dumps(
                {
                    "scoring_version": n.scoring_version,
                    "reason_codes": list(n.reason_codes),
                    "reasons": list(n.reasons),
                },
                ensure_ascii=False,
            ),
        }
