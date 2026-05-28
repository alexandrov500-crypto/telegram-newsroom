"""Structured publish tracing (one event per attempt / outcome)."""

from __future__ import annotations

import logging
import time
from typing import Any

from utils.structured_log import log_event

logger = logging.getLogger(__name__)


def log_publish_trace(
    *,
    event: str,
    draft_id: int,
    publish_attempt: int = 1,
    channel_id: int | None = None,
    telegram_message_id: int | None = None,
    latency_ms: float | None = None,
    outcome: str = "",
    error: str = "",
    idempotency_key: str = "",
    tx_id: str = "",
    **extra: Any,
) -> None:
    fields: dict[str, Any] = {
        "event": event,
        "draft_id": draft_id,
        "publish_attempt": int(publish_attempt),
        "outcome": outcome or None,
        "channel_id": channel_id,
        "telegram_message_id": telegram_message_id,
        "idempotency_key": idempotency_key or None,
        "tx_id": tx_id or None,
    }
    if latency_ms is not None:
        fields["latency_ms"] = round(float(latency_ms), 2)
    if error:
        fields["error"] = error[:500]
    fields.update({k: v for k, v in extra.items() if v is not None})
    log_event(logger, "publish.trace", **fields)


class PublishTraceTimer:
    """Context helper for latency_ms on publish.trace."""

    def __init__(self) -> None:
        self._t0 = time.perf_counter()

    @property
    def latency_ms(self) -> float:
        return (time.perf_counter() - self._t0) * 1000.0
