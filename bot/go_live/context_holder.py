from __future__ import annotations

from bot.go_live.coordinator import GoLiveCoordinator

_go_live: GoLiveCoordinator | None = None


def install_go_live(coordinator: GoLiveCoordinator | None) -> None:
    global _go_live
    _go_live = coordinator


def get_go_live() -> GoLiveCoordinator | None:
    return _go_live
