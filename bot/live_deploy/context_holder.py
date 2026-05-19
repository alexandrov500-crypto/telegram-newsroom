from __future__ import annotations

from bot.live_deploy.coordinator import LiveDeployCoordinator

_live_deploy: LiveDeployCoordinator | None = None


def install_live_deploy(coordinator: LiveDeployCoordinator | None) -> None:
    global _live_deploy
    _live_deploy = coordinator


def get_live_deploy() -> LiveDeployCoordinator | None:
    return _live_deploy
