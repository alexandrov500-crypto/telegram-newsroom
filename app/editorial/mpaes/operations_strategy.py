"""Operational strategy — stable cadence + aggressive growth without long pauses."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.editorial.mpaes.config import growth_aggression_level
from app.editorial.stability.anti_pause import evaluate_anti_pause


@dataclass(frozen=True)
class OperationalPosture:
    """Strategy + tactics for continuous high-value publishing."""

    anti_pause_active: bool
    publish_gap_minutes: float
    continuity_priority: str
    growth_mode: str
    frequency_tactic: str
    relevance_tactic: str
    attractiveness_tactic: str
    stability_override_allowed: bool
    recommended_publishing_mode: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "anti_pause_active": self.anti_pause_active,
            "publish_gap_minutes": round(self.publish_gap_minutes, 1),
            "continuity_priority": self.continuity_priority,
            "growth_mode": self.growth_mode,
            "frequency_tactic": self.frequency_tactic,
            "relevance_tactic": self.relevance_tactic,
            "attractiveness_tactic": self.attractiveness_tactic,
            "stability_override_allowed": self.stability_override_allowed,
            "recommended_publishing_mode": self.recommended_publishing_mode,
        }


def evaluate_operational_posture(
    *,
    newsroom_tz: str = "Europe/Moscow",
    dual_audience_trust: float = 0.6,
    hub_substitution_score: float = 60.0,
    publishing_mode: str = "core",
) -> OperationalPosture:
    ap = evaluate_anti_pause(newsroom_tz=newsroom_tz)
    aggression = growth_aggression_level()

    if ap.anti_pause_active:
        continuity = "zero_gap_first"
        freq = "elastic_fill_or_digest_immediate"
        relevance = "ship_best_available_with_implication"
        attract = "breaking_or_wrap_anchor"
        rec_mode = "elastic_fill"
    elif ap.publish_gap_minutes >= 60:
        continuity = "pre_pause_acceleration"
        freq = "increase_signal_density_next_slot"
        relevance = "prioritize_cross_domain_synthesis"
        attract = "morning_brief_or_market_shock"
        rec_mode = publishing_mode
    else:
        continuity = "steady_rhythm"
        freq = "ccd_slot_aligned_cadence"
        relevance = "decision_relevance_gate"
        attract = "reference_forward_on_high_substitution"
        rec_mode = publishing_mode

    growth_mode = f"aggressive_{aggression}" if aggression == "high" else f"growth_{aggression}"
    if hub_substitution_score >= 75 and dual_audience_trust >= 0.6:
        attract = "flagship_reference_forward"

    return OperationalPosture(
        anti_pause_active=ap.anti_pause_active,
        publish_gap_minutes=ap.publish_gap_minutes,
        continuity_priority=continuity,
        growth_mode=growth_mode,
        frequency_tactic=freq,
        relevance_tactic=relevance,
        attractiveness_tactic=attract,
        stability_override_allowed=ap.anti_pause_active,
        recommended_publishing_mode=rec_mode,
    )
