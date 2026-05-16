"""Publication / model confidence composition (explainable)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class EditorialConfidence:
    confidence_score: float
    publication_risk_score: float
    ai_quality_score: float
    source_agreement_score: float
    notes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "confidence_score": round(self.confidence_score, 4),
            "publication_risk_score": round(self.publication_risk_score, 4),
            "ai_quality_score": round(self.ai_quality_score, 4),
            "source_agreement_score": round(self.source_agreement_score, 4),
            "notes": list(self.notes),
        }


def compute_editorial_confidence(
    *,
    source_count: int,
    unique_channels: int,
    editorial_scores: dict[str, float] | None,
    ai_generation: dict[str, Any] | None,
    duplicate_confidence: float | None,
) -> EditorialConfidence:
    notes: list[str] = []
    es = editorial_scores or {}
    ai_conf = float(es.get("ai_confidence_estimate") or 0.5)
    dup_conf = float(duplicate_confidence or es.get("duplicate_confidence") or 0.0)

    src_div = unique_channels / max(1, source_count)
    source_agreement = round(max(0.0, min(1.0, 0.35 + 0.45 * src_div + 0.12 * min(source_count, 8) / 8.0)), 4)

    ai_gen = ai_generation or {}
    warns = list(ai_gen.get("safety_warnings") or [])
    ai_quality = 0.72
    if warns:
        ai_quality = max(0.25, 0.72 - 0.07 * min(len(warns), 6))
        notes.append("ai_safety_warnings")
    rtok = ai_gen.get("total_tokens")
    if rtok is None:
        notes.append("missing_token_usage")

    publication_risk = round(max(0.0, min(1.0, 0.45 * dup_conf + 0.35 * (1.0 - ai_quality) + 0.2 * (1.0 - source_agreement))), 4)
    confidence = round(max(0.0, min(1.0, 0.5 * ai_conf + 0.35 * ai_quality + 0.15 * source_agreement - 0.12 * dup_conf)), 4)

    return EditorialConfidence(
        confidence_score=confidence,
        publication_risk_score=publication_risk,
        ai_quality_score=round(ai_quality, 4),
        source_agreement_score=source_agreement,
        notes=tuple(notes),
    )
