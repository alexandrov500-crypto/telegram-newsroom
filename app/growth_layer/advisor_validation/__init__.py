"""Advisor effectiveness validation (Phase 3B)."""

from app.growth_layer.advisor_validation.adoption import detect_recommendation_adoption
from app.growth_layer.advisor_validation.causal_analysis import (
    calculate_advisor_reliability,
    compare_adopted_vs_ignored,
    compare_advice_vs_no_advice,
    rank_recommendations,
)
from app.growth_layer.advisor_validation.effectiveness import evaluate_recommendation_effectiveness
from app.growth_layer.advisor_validation.reporting import (
    build_advisor_effectiveness_snapshot,
    persist_advisor_effectiveness_snapshot,
)

__all__ = [
    "detect_recommendation_adoption",
    "evaluate_recommendation_effectiveness",
    "compare_advice_vs_no_advice",
    "compare_adopted_vs_ignored",
    "rank_recommendations",
    "calculate_advisor_reliability",
    "build_advisor_effectiveness_snapshot",
    "persist_advisor_effectiveness_snapshot",
]
