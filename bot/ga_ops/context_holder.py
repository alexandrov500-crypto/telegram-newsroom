from __future__ import annotations

from bot.ga_ops.coordinator import GaOpsCoordinator

_ga_ops: GaOpsCoordinator | None = None


def install_ga_ops(coordinator: GaOpsCoordinator | None) -> None:
    global _ga_ops
    _ga_ops = coordinator


def get_ga_ops() -> GaOpsCoordinator | None:
    return _ga_ops
