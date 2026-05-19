from __future__ import annotations

from bot.platform.coordinator import PlatformCoordinator

_platform: PlatformCoordinator | None = None


def install_platform(coordinator: PlatformCoordinator | None) -> None:
    global _platform
    _platform = coordinator


def get_platform() -> PlatformCoordinator | None:
    return _platform
