from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot.operational_memory.coordinator import OperationalMemoryCoordinator

_coordinator: OperationalMemoryCoordinator | None = None


def install_opmem(coordinator: OperationalMemoryCoordinator) -> None:
    global _coordinator
    _coordinator = coordinator


def get_opmem() -> OperationalMemoryCoordinator | None:
    return _coordinator
