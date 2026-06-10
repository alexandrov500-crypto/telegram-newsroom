"""Hub reader personas — demographic cognitive segments without stereotype spam."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class DemographicSegment(str, Enum):
    """Primary adaptive segments for dual-audience hub channel."""

    HUB_MALE = "hub_male"
    HUB_FEMALE = "hub_female"
    REFERENCE_OPERATOR_MALE = "reference_operator_male"


@dataclass(frozen=True)
class PersonaProfile:
    segment: DemographicSegment
    label: str
    description: str
    topic_weights: dict[str, float]
    framing_preferences: tuple[str, ...]
    frustration_triggers: tuple[str, ...]
    trust_signals: tuple[str, ...]
    cognitive_load_limit: str
    attention_span: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment": self.segment.value,
            "label": self.label,
            "description": self.description,
            "topic_weights": dict(self.topic_weights),
            "framing_preferences": list(self.framing_preferences),
            "frustration_triggers": list(self.frustration_triggers),
            "trust_signals": list(self.trust_signals),
            "cognitive_load_limit": self.cognitive_load_limit,
            "attention_span": self.attention_span,
        }


# Reference operator male — modeled from multi-channel overload pattern:
# Canada/international news, macro economy, SVO/geopolitics, crypto, local city.
REFERENCE_OPERATOR_MALE = PersonaProfile(
    segment=DemographicSegment.REFERENCE_OPERATOR_MALE,
    label="Reference Hub Reader (Male)",
    description=(
        "Subscribes to 10–20 channels: macro wires, geo breaking, crypto, local city, "
        "business earnings. Wants one trusted feed that replaces the stack."
    ),
    topic_weights={
        "macro": 0.88,
        "geopolitics": 0.92,
        "crypto": 0.78,
        "local": 0.72,
        "markets": 0.85,
        "ai": 0.70,
        "business": 0.75,
        "energy": 0.65,
    },
    framing_preferences=(
        "decision_relevance_first",
        "implication_in_one_sentence",
        "cross_domain_synthesis",
        "no_duplicate_ru_macro_streams",
    ),
    frustration_triggers=(
        "ten_source_recap",
        "news_for_news",
        "repetition_across_posts",
        "noise_without_implication",
    ),
    trust_signals=(
        "why_it_matters",
        "source_independence",
        "consistent_cadence",
        "breaking_only_when_real",
    ),
    cognitive_load_limit="medium",
    attention_span="short_to_medium",
)

HUB_MALE = PersonaProfile(
    segment=DemographicSegment.HUB_MALE,
    label="Hub Male Reader",
    description="Professional male reader seeking clarity across macro, markets, geo, tech.",
    topic_weights={
        "macro": 0.85,
        "markets": 0.82,
        "geopolitics": 0.80,
        "ai": 0.75,
        "crypto": 0.70,
        "business": 0.72,
        "energy": 0.60,
        "local": 0.55,
    },
    framing_preferences=(
        "direct_implication",
        "structural_context",
        "actionable_decision_frame",
    ),
    frustration_triggers=("jargon_without_context", "lifestyle_soft_bias", "subscribe_spam"),
    trust_signals=("verified_sources", "consistent_voice", "evening_wrap_closure"),
    cognitive_load_limit="medium",
    attention_span="short_to_medium",
)

HUB_FEMALE = PersonaProfile(
    segment=DemographicSegment.HUB_FEMALE,
    label="Hub Female Reader",
    description="Professional female reader — same information density, impact-first framing.",
    topic_weights={
        "macro": 0.80,
        "geopolitics": 0.78,
        "business": 0.75,
        "ai": 0.72,
        "markets": 0.70,
        "science": 0.68,
        "local": 0.65,
        "energy": 0.58,
    },
    framing_preferences=(
        "impact_on_daily_decisions",
        "context_before_detail",
        "trust_through_clarity",
        "no_masculine_coded_hype",
    ),
    frustration_triggers=(
        "masculine_coded_framing",
        "horoscope_lifestyle_noise",
        "unexplained_jargon",
        "news_without_why",
    ),
    trust_signals=("gender_neutral_clarity", "implication_sentence", "no_hype"),
    cognitive_load_limit="medium",
    attention_span="short_to_medium",
)

_PERSONAS: dict[DemographicSegment, PersonaProfile] = {
    DemographicSegment.REFERENCE_OPERATOR_MALE: REFERENCE_OPERATOR_MALE,
    DemographicSegment.HUB_MALE: HUB_MALE,
    DemographicSegment.HUB_FEMALE: HUB_FEMALE,
}


def all_hub_personas() -> list[PersonaProfile]:
    return [HUB_MALE, HUB_FEMALE, REFERENCE_OPERATOR_MALE]


def get_persona(segment: DemographicSegment) -> PersonaProfile:
    return _PERSONAS[segment]
