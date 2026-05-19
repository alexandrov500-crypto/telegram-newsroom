from __future__ import annotations

from bot.production_safety.coordinator import ProductionSafetyCoordinator

_coordinator: ProductionSafetyCoordinator | None = None


def install_production_safety(coordinator: ProductionSafetyCoordinator | None) -> None:
    global _coordinator
    _coordinator = coordinator


def get_production_safety() -> ProductionSafetyCoordinator | None:
    return _coordinator
