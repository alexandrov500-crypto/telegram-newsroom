"""Platformization layer — plugins, workflows, policy, graph, IDP, gateway."""

from bot.platform.context_holder import get_platform, install_platform
from bot.platform.coordinator import PlatformCoordinator
from bot.platform.factory import build_platform_stack

__all__ = [
    "PlatformCoordinator",
    "build_platform_stack",
    "get_platform",
    "install_platform",
]
