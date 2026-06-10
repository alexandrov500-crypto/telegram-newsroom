"""Score content fit per demographic hub segment."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.editorial.mpaes.hub_substitution_map import infer_vertical
from app.editorial.mpaes.persona_registry import (
    DemographicSegment,
    PersonaProfile,
    all_hub_personas,
    get_persona,
)


@dataclass(frozen=True)
class SegmentFitResult:
    segment: DemographicSegment
    relevance_score: float
    trust_score: float
    overload_risk: float
    passes: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment": self.segment.value,
            "relevance_score": round(self.relevance_score, 2),
            "trust_score": round(self.trust_score, 2),
            "overload_risk": round(self.overload_risk, 2),
            "passes": self.passes,
        }


_NOISE = re.compile(r"(подписывайтесь|subscribe|follow\s+us|новости\s+ради\s+новост)", re.I)
_WHY = re.compile(r"(почему\s+важно|why\s+it\s+matters|что\s+дальше|implication|значит\s+для)", re.I)
_MASCULINE = re.compile(r"(alpha\s+male|bro\b|red\s+pill|based\b)", re.I)
_LIFESTYLE = re.compile(r"(гороскоп|beauty\s+tip|relationship\s+advice)", re.I)
_RECAP = re.compile(r"(по\s+данным\s+\d+|источник[аи]:\s*\d+|10\s+канал)", re.I)


def _score_persona(text: str, persona: PersonaProfile, vertical: str) -> SegmentFitResult:
    t = text or ""
    weights = persona.topic_weights
    relevance = float(weights.get(vertical, 0.55)) * 100.0

    if _WHY.search(t):
        relevance += 12.0
    if len(t) >= 120:
        relevance += 5.0

    trust = 70.0
    overload = 15.0

    if _NOISE.search(t):
        trust -= 30.0
        overload += 20.0
    if _RECAP.search(t):
        trust -= 20.0
        overload += 25.0

    if persona.segment == DemographicSegment.HUB_FEMALE:
        if _MASCULINE.search(t):
            trust -= 25.0
        if _LIFESTYLE.search(t):
            trust -= 15.0
    if persona.segment in {DemographicSegment.HUB_MALE, DemographicSegment.REFERENCE_OPERATOR_MALE}:
        if _LIFESTYLE.search(t):
            trust -= 10.0

    relevance = min(100.0, relevance)
    trust = max(0.0, min(100.0, trust))
    overload = max(0.0, min(100.0, overload))

    passes = trust >= 50.0 and relevance >= 45.0 and overload < 65.0

    return SegmentFitResult(
        segment=persona.segment,
        relevance_score=relevance,
        trust_score=trust,
        overload_risk=overload,
        passes=passes,
    )


def evaluate_all_segments(
    text: str,
    *,
    editorial_category: str = "",
) -> dict[str, Any]:
    vertical = infer_vertical(text, editorial_category)
    results = [_score_persona(text, p, vertical) for p in all_hub_personas()]

    male = next(r for r in results if r.segment == DemographicSegment.HUB_MALE)
    female = next(r for r in results if r.segment == DemographicSegment.HUB_FEMALE)
    ref = next(r for r in results if r.segment == DemographicSegment.REFERENCE_OPERATOR_MALE)

    dual_trust = (male.trust_score + female.trust_score) / 200.0
    dual_relevance = (male.relevance_score + female.relevance_score) / 200.0
    max_overload = max(r.overload_risk for r in results)

    return {
        "vertical": vertical,
        "segments": [r.to_dict() for r in results],
        "dual_audience_trust": round(dual_trust, 3),
        "dual_audience_relevance": round(dual_relevance, 3),
        "reference_operator_fit": round(ref.relevance_score / 100.0, 3),
        "max_overload_risk": round(max_overload, 2),
        "dual_passes": male.passes and female.passes,
        "all_pass": all(r.passes for r in results),
    }


def primary_segment_for_content(text: str, editorial_category: str = "") -> DemographicSegment:
    vertical = infer_vertical(text, editorial_category)
    male_w = get_persona(DemographicSegment.HUB_MALE).topic_weights.get(vertical, 0.5)
    female_w = get_persona(DemographicSegment.HUB_FEMALE).topic_weights.get(vertical, 0.5)
    if male_w >= female_w + 0.08:
        return DemographicSegment.HUB_MALE
    if female_w >= male_w + 0.08:
        return DemographicSegment.HUB_FEMALE
    return DemographicSegment.REFERENCE_OPERATOR_MALE
