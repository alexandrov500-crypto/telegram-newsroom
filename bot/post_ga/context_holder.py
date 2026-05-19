from __future__ import annotations

from bot.post_ga.coordinator import PostGaCoordinator

_post_ga: PostGaCoordinator | None = None


def install_post_ga(coordinator: PostGaCoordinator | None) -> None:
    global _post_ga
    _post_ga = coordinator


def get_post_ga() -> PostGaCoordinator | None:
    return _post_ga
