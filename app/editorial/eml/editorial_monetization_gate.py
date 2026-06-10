"""Editorial-safe monetization gate — bridges to W5 revenue engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.editorial.eml.config import min_attention_value, monetization_stress_max
from app.editorial.eml.revenue_abstraction import RevenueAbstractionState


@dataclass(frozen=True)
class EditorialMonetizationVerdict:
    allow_monetization: bool
    allow_sponsor: bool
    allow_premium_split: bool
    allow_conversion_cta: bool
    stress_score: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "allow_monetization": self.allow_monetization,
            "allow_sponsor": self.allow_sponsor,
            "allow_premium_split": self.allow_premium_split,
            "allow_conversion_cta": self.allow_conversion_cta,
            "stress_score": round(self.stress_score, 3),
            "reason": self.reason,
        }


def evaluate_editorial_monetization_gate(
    revenue: RevenueAbstractionState,
    *,
    cognitive_value: float,
    publish_approved: bool,
) -> EditorialMonetizationVerdict:
    stress = max(0.0, 1.0 - cognitive_value)
    if not publish_approved or cognitive_value < min_attention_value():
        return EditorialMonetizationVerdict(
            allow_monetization=False,
            allow_sponsor=False,
            allow_premium_split=False,
            allow_conversion_cta=False,
            stress_score=stress,
            reason="editorial_gate_low_value",
        )

    if stress >= monetization_stress_max():
        return EditorialMonetizationVerdict(
            allow_monetization=False,
            allow_sponsor=False,
            allow_premium_split=False,
            allow_conversion_cta=False,
            stress_score=stress,
            reason="monetization_stress_cap",
        )

    allow = revenue.monetization_allowed
    sponsor = allow and revenue.mode.value in {"soft_funnel", "syndication_ready"}
    premium = allow and revenue.mode.value == "premium_candidate"
    cta = allow and revenue.mode.value in {"soft_funnel", "premium_candidate"}

    return EditorialMonetizationVerdict(
        allow_monetization=allow,
        allow_sponsor=sponsor,
        allow_premium_split=premium,
        allow_conversion_cta=cta,
        stress_score=stress,
        reason=revenue.reason,
    )
