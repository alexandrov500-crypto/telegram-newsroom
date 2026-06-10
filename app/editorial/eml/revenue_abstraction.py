"""Value → revenue abstraction without editorial spam."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.editorial.eml.attention_value_model import AttentionValueState


class RevenueAbstractionMode(str, Enum):
    ORGANIC_ONLY = "organic_only"
    SOFT_FUNNEL = "soft_funnel"
    PREMIUM_CANDIDATE = "premium_candidate"
    SYNDICATION_READY = "syndication_ready"
    BLOCKED_EDITORIAL = "blocked_editorial"


@dataclass(frozen=True)
class RevenueAbstractionState:
    mode: RevenueAbstractionMode
    estimated_value_index: float
    revenue_stream_hint: str
    monetization_allowed: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "estimated_value_index": round(self.estimated_value_index, 3),
            "revenue_stream_hint": self.revenue_stream_hint,
            "monetization_allowed": self.monetization_allowed,
            "reason": self.reason,
        }


def abstract_revenue_potential(
    attention: AttentionValueState,
    *,
    editorial_category: str = "macro",
    is_breaking: bool = False,
    mdi_score: float = 50.0,
    monetization_stress: float = 0.0,
) -> RevenueAbstractionState:
    if is_breaking or monetization_stress >= 0.65:
        return RevenueAbstractionState(
            mode=RevenueAbstractionMode.BLOCKED_EDITORIAL,
            estimated_value_index=attention.cognitive_value_score,
            revenue_stream_hint="organic",
            monetization_allowed=False,
            reason="breaking_or_stress_cap",
        )

    value_idx = attention.cognitive_value_score * 0.5 + mdi_score / 100.0 * 0.3 + attention.substitution_value * 0.2

    if value_idx >= 0.75 and attention.trust_accumulation >= 0.65:
        return RevenueAbstractionState(
            mode=RevenueAbstractionMode.PREMIUM_CANDIDATE,
            estimated_value_index=value_idx,
            revenue_stream_hint="premium",
            monetization_allowed=True,
            reason="high_trust_substitution",
        )
    if value_idx >= 0.62:
        return RevenueAbstractionState(
            mode=RevenueAbstractionMode.SYNDICATION_READY,
            estimated_value_index=value_idx,
            revenue_stream_hint="syndication",
            monetization_allowed=True,
            reason="cross_domain_value",
        )
    if value_idx >= 0.48:
        return RevenueAbstractionState(
            mode=RevenueAbstractionMode.SOFT_FUNNEL,
            estimated_value_index=value_idx,
            revenue_stream_hint="organic",
            monetization_allowed=True,
            reason="reference_forward_funnel",
        )

    return RevenueAbstractionState(
        mode=RevenueAbstractionMode.ORGANIC_ONLY,
        estimated_value_index=value_idx,
        revenue_stream_hint="organic",
        monetization_allowed=False,
        reason="build_trust_first",
    )
