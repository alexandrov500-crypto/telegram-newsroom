"""Typed containers for editorial scoring (rule-based; no ML)."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(slots=True)
class EditorialScoreCard:
    freshness: float
    source_reliability: float
    topic_importance: float
    spam_likelihood: float
    duplicate_confidence: float
    ai_confidence_estimate: float

    def to_dict(self) -> dict[str, float]:
        return {k: round(float(v), 4) for k, v in asdict(self).items()}
