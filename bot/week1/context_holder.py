from __future__ import annotations

from bot.week1.coordinator import Week1Coordinator

_week1: Week1Coordinator | None = None


def install_week1(coordinator: Week1Coordinator | None) -> None:
    global _week1
    _week1 = coordinator


def get_week1() -> Week1Coordinator | None:
    return _week1
