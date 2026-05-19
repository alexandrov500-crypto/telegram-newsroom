from __future__ import annotations

from bot.signals.types import CredibilityProfile, EditorialAction, ImpactProfile, PriorityDecision


def compute_editorial_priority(
    *,
    importance: float,
    novelty: float,
    acceleration: float,
    credibility: CredibilityProfile,
    forecast_probability: float,
    expected_impact: float,
    language_count: int = 1,
    entity_centrality: float = 0.0,
) -> PriorityDecision:
    lang_spread = min(1.0, language_count / 2.0)
    score = (
        importance * 0.22
        + novelty * 0.14
        + acceleration * 0.16
        + credibility.credibility_score * 0.14
        + forecast_probability * 0.14
        + expected_impact * 0.12
        + lang_spread * 0.04
        + entity_centrality * 0.04
    )
    score = max(0.0, min(1.0, score))

    if score >= 0.88 and credibility.risk_score < 0.45 and forecast_probability >= 0.75:
        action = EditorialAction.PUBLISH_IMMEDIATELY.value
        reason = "high_confidence_breaking"
    elif credibility.risk_score >= 0.65 or credibility.sensationalism >= 0.5:
        action = EditorialAction.WAIT_CONFIRMATION.value
        reason = "credibility_risk"
    elif score >= 0.78 and forecast_probability >= 0.7:
        action = EditorialAction.ESCALATE_ADMIN.value
        reason = "likely_escalation"
    elif score < 0.32 or credibility.credibility_score < 0.25:
        action = EditorialAction.SUPPRESS.value
        reason = "low_quality_noise"
    elif score < 0.55:
        action = EditorialAction.DIGEST_ONLY.value
        reason = "moderate_priority_digest"
    elif score >= 0.65:
        action = EditorialAction.WAIT_CONFIRMATION.value
        reason = "await_corroboration"
    else:
        action = EditorialAction.DIGEST_ONLY.value
        reason = "default_digest_path"

    return PriorityDecision(
        editorial_priority_score=score,
        action=action,
        reason=reason,
    )
