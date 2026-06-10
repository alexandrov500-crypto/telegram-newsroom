"""Editorial portfolio strategy intelligence (Phase 4A)."""

from app.growth_layer.strategy.growth_budget import simulate_growth_budget_shift
from app.growth_layer.strategy.opportunity_detection import detect_growth_opportunities
from app.growth_layer.strategy.portfolio_analysis import build_portfolio_analysis
from app.growth_layer.strategy.segment_allocation import recommend_content_allocation
from app.growth_layer.strategy.strategy_reporting import (
    build_editorial_strategy_snapshot,
    persist_editorial_strategy_snapshot,
)
from app.growth_layer.strategy.strategy_scorecard import build_strategy_scorecard

__all__ = [
    "build_portfolio_analysis",
    "detect_growth_opportunities",
    "recommend_content_allocation",
    "simulate_growth_budget_shift",
    "build_strategy_scorecard",
    "build_editorial_strategy_snapshot",
    "persist_editorial_strategy_snapshot",
]
