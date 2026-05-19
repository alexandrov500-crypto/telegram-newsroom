from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot.staging.shadow_publish import StagingPublishGuard

_publish_guard: StagingPublishGuard | None = None


def install_publish_guard(guard: StagingPublishGuard | None) -> None:
    global _publish_guard
    _publish_guard = guard


def get_publish_guard() -> StagingPublishGuard | None:
    return _publish_guard
