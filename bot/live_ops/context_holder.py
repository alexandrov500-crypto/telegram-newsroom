from __future__ import annotations

from typing import TYPE_CHECKING

from bot.live_ops.coordinator import LiveOpsCoordinator

if TYPE_CHECKING:
    from bot.live_ops.controlled_coordinator import ControlledLiveCoordinator

_live_ops: LiveOpsCoordinator | None = None
_controlled_live: ControlledLiveCoordinator | None = None


def install_live_ops(coordinator: LiveOpsCoordinator | None) -> None:
    global _live_ops
    _live_ops = coordinator


def get_live_ops() -> LiveOpsCoordinator | None:
    return _live_ops


def install_controlled_live(coordinator: ControlledLiveCoordinator | None) -> None:
    global _controlled_live
    _controlled_live = coordinator


def get_controlled_live() -> ControlledLiveCoordinator | None:
    return _controlled_live
