from __future__ import annotations

from bot.rc1.coordinator import Rc1Coordinator

_rc1: Rc1Coordinator | None = None


def install_rc1(coordinator: Rc1Coordinator | None) -> None:
    global _rc1
    _rc1 = coordinator


def get_rc1() -> Rc1Coordinator | None:
    return _rc1
