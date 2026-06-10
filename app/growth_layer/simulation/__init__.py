"""Editorial strategy simulation sandbox (Phase 4C)."""

from app.growth_layer.simulation.impact_estimator import estimate_strategy_impact
from app.growth_layer.simulation.portfolio_simulation import simulate_portfolio_shift
from app.growth_layer.simulation.scenario_builder import build_strategy_scenarios
from app.growth_layer.simulation.simulation_report import (
    build_editorial_simulation_snapshot,
    check_scenario_alignment,
    load_editorial_simulation_snapshot,
    persist_editorial_simulation_snapshot,
    simulate_top_scenarios,
)
from app.growth_layer.simulation.strategy_simulator import simulate_strategy
from app.growth_layer.simulation.what_if_engine import run_what_if_simulation

__all__ = [
    "build_strategy_scenarios",
    "run_what_if_simulation",
    "simulate_strategy",
    "simulate_portfolio_shift",
    "estimate_strategy_impact",
    "build_editorial_simulation_snapshot",
    "persist_editorial_simulation_snapshot",
    "load_editorial_simulation_snapshot",
    "simulate_top_scenarios",
    "check_scenario_alignment",
]
