"""User journey simulation — persona satisfaction and overload."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class PersonaType(str, Enum):
    MACRO_HEAVY = "macro_heavy"
    TECH_HEAVY = "tech_heavy"
    MIXED_INVESTOR = "mixed_investor"
    CASUAL_INTELLIGENCE = "casual_intelligence"


_PERSONA_WEIGHTS: dict[PersonaType, dict[str, float]] = {
    PersonaType.MACRO_HEAVY: {"macro": 0.9, "markets": 0.85, "geopolitics": 0.7, "ai": 0.5},
    PersonaType.TECH_HEAVY: {"ai": 0.95, "tech": 0.9, "markets": 0.6, "macro": 0.5},
    PersonaType.MIXED_INVESTOR: {"macro": 0.8, "markets": 0.85, "ai": 0.7, "geopolitics": 0.65},
    PersonaType.CASUAL_INTELLIGENCE: {"macro": 0.6, "geopolitics": 0.55, "ai": 0.5, "business": 0.5},
}


@dataclass(frozen=True)
class PersonaJourneyResult:
    persona: PersonaType
    daily_satisfaction: float
    return_probability: float
    overload_probability: float
    substitution_success_rate: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "persona": self.persona.value,
            "daily_satisfaction": round(self.daily_satisfaction, 3),
            "return_probability": round(self.return_probability, 3),
            "overload_probability": round(self.overload_probability, 3),
            "substitution_success_rate": round(self.substitution_success_rate, 3),
        }


def simulate_persona_journey(
    *,
    persona: PersonaType,
    category: str,
    binding_score: float,
    experience_fit: float,
    posts_today: int,
    substitution_score: float,
) -> PersonaJourneyResult:
    weights = _PERSONA_WEIGHTS.get(persona, _PERSONA_WEIGHTS[PersonaType.MIXED_INVESTOR])
    cat_fit = weights.get(category, 0.45)

    satisfaction = 0.35 * cat_fit + 0.25 * (binding_score / 100.0) + 0.40 * experience_fit
    satisfaction = min(1.0, max(0.0, satisfaction))

    overload = min(1.0, max(0.0, posts_today / 8.0 * 0.6 + (1.0 - binding_score / 100.0) * 0.4))
    ret = min(1.0, satisfaction * 0.7 + (1.0 - overload) * 0.3)
    subst = min(1.0, substitution_score / 100.0 * 0.6 + satisfaction * 0.4)

    return PersonaJourneyResult(
        persona=persona,
        daily_satisfaction=satisfaction,
        return_probability=ret,
        overload_probability=overload,
        substitution_success_rate=subst,
    )


def simulate_all_personas(**kwargs: Any) -> dict[str, Any]:
    results = [simulate_persona_journey(persona=p, **kwargs).to_dict() for p in PersonaType]
    avg_sat = sum(r["daily_satisfaction"] for r in results) / len(results)
    avg_ret = sum(r["return_probability"] for r in results) / len(results)
    return {
        "personas": results,
        "avg_satisfaction": round(avg_sat, 3),
        "avg_return_probability": round(avg_ret, 3),
    }
