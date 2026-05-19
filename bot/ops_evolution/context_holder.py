from __future__ import annotations

from bot.ops_evolution.coordinator import OpsEvolutionCoordinator

_ops_evolution: OpsEvolutionCoordinator | None = None


def install_ops_evolution(coordinator: OpsEvolutionCoordinator | None) -> None:
    global _ops_evolution
    _ops_evolution = coordinator


def get_ops_evolution() -> OpsEvolutionCoordinator | None:
    return _ops_evolution
