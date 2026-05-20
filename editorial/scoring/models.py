"""Typed editorial intelligence scores (Phase 2.1 — explainable heuristics)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


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
    publish_priority_label: str = "medium"
    reasons: list[str] = field(default_factory=list)

    def to_extras_payload(self) -> dict[str, Any]:
        return {
            "quality_score": round(self.quality_score, 4),
            "novelty_score": round(self.novelty_score, 4),
            "source_trust_score": round(self.source_trust_score, 4),
            "duplicate_confidence": round(self.duplicate_confidence, 4),
            "cluster_importance_score": round(self.cluster_importance_score, 4),
            "publish_priority_score": round(self.publish_priority_score, 4),
            "publish_priority": self.publish_priority_label,
            "operator_feedback_score": self.operator_feedback_score,
            "reasons": list(self.reasons),
        }

    def to_db_row(self, *, draft_id: int) -> dict[str, Any]:
        import json

        return {
            "draft_id": draft_id,
            "quality_score": self.quality_score,
            "novelty_score": self.novelty_score,
            "source_trust_score": self.source_trust_score,
            "duplicate_confidence": self.duplicate_confidence,
            "cluster_importance_score": self.cluster_importance_score,
            "publish_priority_score": self.publish_priority_score,
            "operator_feedback_score": self.operator_feedback_score,
            "reasons_json": json.dumps({"reasons": self.reasons}, ensure_ascii=False),
        }
