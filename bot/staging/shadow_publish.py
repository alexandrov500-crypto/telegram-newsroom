from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from bot.runtime.state import runtime_state

if TYPE_CHECKING:
    from bot.operations.repository import OperationsRepository

logger = logging.getLogger(__name__)

SHADOW_MARKER = "[STAGING]"


@dataclass(frozen=True)
class PublishGuardVerdict:
    allowed: bool
    reason: str
    correlation_id: str
    shadow: bool


class StagingPublishGuard:
    """Shadow-only publishing with production channel blocklist and audit."""

    def __init__(
        self,
        *,
        staging_mode: bool,
        shadow_only: bool,
        blocked_channel_ids: frozenset[int],
        repository: OperationsRepository | None = None,
    ) -> None:
        self._staging = staging_mode
        self._shadow_only = shadow_only
        self._blocked = blocked_channel_ids
        self._repo = repository

    def evaluate_channel(self, channel_id: int | None) -> PublishGuardVerdict:
        cid = str(uuid.uuid4())[:12]
        if channel_id is None:
            return PublishGuardVerdict(False, "channel_not_configured", cid, self._staging)
        if channel_id in self._blocked:
            logger.error("event=staging_production_channel_blocked channel_id=%s", channel_id)
            return PublishGuardVerdict(False, "production_channel_blocked", cid, True)
        if self._shadow_only or self._staging:
            return PublishGuardVerdict(True, "shadow_staging_ok", cid, True)
        return PublishGuardVerdict(True, "ok", cid, False)

    def decorate_message(self, text: str, *, correlation_id: str) -> str:
        if not (self._staging or runtime_state.shadow_publish_only):
            return text
        if text.startswith(SHADOW_MARKER):
            return text
        return f"{SHADOW_MARKER} {text}\n\n<i>shadow publish · {correlation_id}</i>"

    def record_audit(
        self,
        *,
        pending_news_id: int | None,
        channel_id: int | None,
        correlation_id: str,
        approved: bool,
        operator_id: str | None = None,
        detail: dict | None = None,
    ) -> None:
        if self._repo is None:
            return
        try:
            self._repo.record_staging_publish_audit(
                correlation_id=correlation_id,
                pending_news_id=pending_news_id,
                channel_id=channel_id,
                approved=approved,
                operator_id=operator_id,
                detail=detail or {},
            )
        except Exception:
            logger.exception("event=staging_publish_audit_failed")

    @staticmethod
    def now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()
