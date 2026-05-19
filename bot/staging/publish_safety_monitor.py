from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from aiogram import Bot
    from bot.staging.shadow_publish import StagingPublishGuard

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PublishSafetyReport:
    channel_ok: bool
    shadow_enforced: bool
    blocklist_ok: bool
    recent_audit_ok: bool
    issues: list[str]


class PublishSafetyMonitor:
    """Continuous shadow-publish and channel permission validation."""

    def __init__(self, guard: StagingPublishGuard, repository: Any | None = None) -> None:
        self._guard = guard
        self._repo = repository

    async def check_channel_permissions(
        self,
        bot: Bot,
        channel_id: int | None,
    ) -> PublishSafetyReport:
        issues: list[str] = []
        channel_ok = False
        if channel_id is None:
            issues.append("channel_not_configured")
        else:
            try:
                chat = await bot.get_chat(channel_id)
                channel_ok = chat is not None
            except Exception as exc:
                issues.append(f"channel_probe_failed:{exc}")
        verdict = self._guard.evaluate_channel(channel_id)
        if not verdict.allowed:
            issues.append(f"guard_blocked:{verdict.reason}")
        shadow = verdict.shadow or self._guard._shadow_only
        blocklist_ok = channel_id not in self._guard._blocked if channel_id else True
        audit_ok = True
        if self._repo is not None:
            mismatches = self._repo.staging_publish_mismatch_count(hours=24)
            if mismatches > 0:
                audit_ok = False
                issues.append(f"publish_audit_mismatches:{mismatches}")
        return PublishSafetyReport(
            channel_ok=channel_ok,
            shadow_enforced=shadow,
            blocklist_ok=blocklist_ok,
            recent_audit_ok=audit_ok,
            issues=issues,
        )
