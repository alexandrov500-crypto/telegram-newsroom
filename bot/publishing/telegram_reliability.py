from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeliveryAudit:
    message_key: str
    channel_id: int
    success: bool
    latency_ms: int
    message_id: int | None = None
    error: str | None = None
    duplicate_prevented: bool = False


class TelegramDeliveryReliability:
    """Outbound audit, deduplication, and delivery metrics for Telegram."""

    def __init__(self, repository: Any | None = None) -> None:
        self._repo = repository
        self._recent_keys: dict[str, float] = {}
        self._dedup_ttl_sec = 3600.0

    @staticmethod
    def message_key(*, channel_id: int, pending_news_id: int | None, content_hash: str) -> str:
        base = f"{channel_id}:{pending_news_id or 0}:{content_hash}"
        return hashlib.sha256(base.encode()).hexdigest()[:20]

    def should_send(self, message_key: str) -> bool:
        now = time.monotonic()
        self._prune(now)
        if message_key in self._recent_keys:
            try:
                from bot.observability.metrics import record_telegram_duplicate_prevented

                record_telegram_duplicate_prevented()
            except Exception:
                pass
            return False
        self._recent_keys[message_key] = now
        return True

    def _prune(self, now: float) -> None:
        expired = [k for k, t in self._recent_keys.items() if now - t > self._dedup_ttl_sec]
        for k in expired:
            del self._recent_keys[k]

    def record_delivery(self, audit: DeliveryAudit) -> None:
        if self._repo is not None:
            try:
                self._repo.record_telegram_outbound(
                    message_key=audit.message_key,
                    channel_id=audit.channel_id,
                    success=audit.success,
                    latency_ms=audit.latency_ms,
                    message_id=audit.message_id,
                    error=audit.error,
                )
            except Exception:
                logger.debug("event=telegram_outbound_audit_skipped")
        try:
            from bot.observability.metrics import (
                observe_telegram_delivery_latency,
                record_telegram_delivery_failure,
            )

            observe_telegram_delivery_latency(audit.latency_ms / 1000.0)
            if not audit.success:
                record_telegram_delivery_failure()
        except Exception:
            pass
