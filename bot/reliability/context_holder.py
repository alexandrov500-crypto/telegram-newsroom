from __future__ import annotations

from bot.reliability.coordinator import ReliabilityCoordinator

_reliability: ReliabilityCoordinator | None = None


def install_reliability(coordinator: ReliabilityCoordinator | None) -> None:
    global _reliability
    _reliability = coordinator


def get_reliability() -> ReliabilityCoordinator | None:
    return _reliability
