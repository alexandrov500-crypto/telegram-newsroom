from __future__ import annotations

URGENCY_BREAKING = "breaking"
URGENCY_SIGNIFICANT = "significant"
URGENCY_ROUTINE = "routine"
URGENCY_BACKGROUND = "background"
URGENCY_LOW = "low-priority"


def classify_urgency(
    *,
    editorial_priority_score: float,
    momentum: float,
    novelty: float,
    market_impact: float,
    geopolitical_impact: float,
    is_duplicate_follow_up: bool,
) -> str:
    if is_duplicate_follow_up and editorial_priority_score < 0.55:
        return URGENCY_LOW
    if editorial_priority_score >= 0.82 and (momentum >= 0.6 or market_impact >= 0.75):
        return URGENCY_BREAKING
    if editorial_priority_score >= 0.68 and (
        momentum >= 0.45 or geopolitical_impact >= 0.7 or market_impact >= 0.65
    ):
        return URGENCY_SIGNIFICANT
    if editorial_priority_score >= 0.48:
        return URGENCY_ROUTINE
    if editorial_priority_score >= 0.32:
        return URGENCY_BACKGROUND
    return URGENCY_LOW
