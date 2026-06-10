"""Adaptive narrative tuning — trusted framing for male + female hub readers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.editorial.audience_unification.communication_balance import evaluate_communication_balance
from app.editorial.mpaes.cognitive_segmentation import primary_segment_for_content
from app.editorial.mpaes.persona_registry import DemographicSegment


@dataclass(frozen=True)
class NarrativeAdaptation:
    applied: bool
    adaptation_type: str
    dual_trust_boost: float
    body: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "applied": self.applied,
            "adaptation_type": self.adaptation_type,
            "dual_trust_boost": round(self.dual_trust_boost, 2),
            "primary_segment": primary_segment_for_content(self.body).value,
        }


_WHY_MISSING = re.compile(r"(почему\s+важно|why\s+it\s+matters|что\s+это\s+значит|implication)", re.I)


def adapt_narrative_for_dual_audience(
    body: str,
    *,
    editorial_category: str = "",
    is_breaking: bool = False,
) -> NarrativeAdaptation:
    text = (body or "").strip()
    if not text or is_breaking:
        return NarrativeAdaptation(applied=False, adaptation_type="none", dual_trust_boost=0.0, body=text)

    balance = evaluate_communication_balance(text)
    segment = primary_segment_for_content(text, editorial_category)
    adapted = text
    adaptation_type = "none"
    boost = 0.0

    if not _WHY_MISSING.search(text) and len(text) >= 80:
        if segment == DemographicSegment.HUB_FEMALE:
            suffix = "\n\nПочему важно: влияет на решения и контекст недели — без лишнего шума."
        else:
            suffix = "\n\nПочему важно: меняет расчёт риска и приоритеты на ближайшие дни."
        adapted = text + suffix
        adaptation_type = "implication_injection"
        boost = 8.0

    if not balance.passes and "masculine_coded_framing" in balance.issues:
        adapted = re.sub(
            r"(alpha\s+male|bro\b|red\s+pill|based\b)",
            "",
            adapted,
            flags=re.I,
        ).strip()
        adaptation_type = "masculine_coded_strip"
        boost += 5.0

    return NarrativeAdaptation(
        applied=adaptation_type != "none",
        adaptation_type=adaptation_type,
        dual_trust_boost=boost,
        body=adapted,
    )
