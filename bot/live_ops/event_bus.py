from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from bot.events.envelope import EventEnvelope
from bot.events.validation import is_poison_message, validate_envelope
from bot.live_ops.contracts import LiveEventType, build_envelope
from bot.live_ops.observability.telemetry import LiveOpsTelemetry

logger = logging.getLogger(__name__)

StreamHandler = Callable[[EventEnvelope], Awaitable[None]]


class NewsroomLiveEventBus:
    """
    Unified async event bus: typed contracts, correlation IDs, DLQ, replay hooks.
    Delegates to StreamEventBus (Redis) or in-process EventBus without breaking callers.
    """

    def __init__(
        self,
        *,
        stream_bus: Any | None = None,
        inprocess_bus: Any | None = None,
        telemetry: LiveOpsTelemetry | None = None,
        max_retries: int = 5,
    ) -> None:
        self._stream = stream_bus
        self._inprocess = inprocess_bus
        self._telemetry = telemetry or LiveOpsTelemetry()
        self._max_retries = max_retries
        self._handlers: dict[str, list[StreamHandler]] = {}

    def subscribe(self, event_type: LiveEventType | str, handler: StreamHandler) -> None:
        key = event_type.value if isinstance(event_type, LiveEventType) else event_type
        self._handlers.setdefault(key, []).append(handler)
        if self._stream is not None and hasattr(self._stream, "subscribe_envelope"):
            self._stream.subscribe_envelope(key, handler)

    async def emit(
        self,
        event_type: LiveEventType,
        payload: dict[str, Any],
        *,
        node_id: str = "local",
        region: str = "global",
        correlation_id: str | None = None,
        causation_id: str | None = None,
    ) -> str | None:
        envelope = build_envelope(
            event_type,
            payload,
            node_id=node_id,
            region=region,
            correlation_id=correlation_id,
            causation_id=causation_id,
        )
        return await self.emit_envelope(envelope)

    async def emit_envelope(self, envelope: EventEnvelope) -> str | None:
        validate_envelope(envelope)
        if is_poison_message(envelope, max_retries=self._max_retries):
            await self._quarantine(envelope, reason="max_retries_exceeded")
            return None

        self._telemetry.record_publish(envelope.event_type)
        msg_id: str | None = None

        if self._inprocess is not None:
            legacy = envelope.to_legacy_event()
            await self._inprocess.publish(legacy)

        if self._stream is not None and hasattr(self._stream, "publish_envelope"):
            try:
                msg_id = await self._stream.publish_envelope(envelope)
            except Exception:
                logger.exception("event=live_bus_stream_publish_failed type=%s", envelope.event_type)
                await self._retry_or_dlq(envelope)
                return None

        for handler in self._handlers.get(envelope.event_type, []):
            try:
                await handler(envelope)
            except Exception:
                logger.exception("event=live_bus_handler_failed type=%s", envelope.event_type)

        return msg_id

    async def _retry_or_dlq(self, envelope: EventEnvelope) -> None:
        if envelope.retry_count < self._max_retries:
            await self.emit_envelope(envelope.with_retry())
        else:
            await self._quarantine(envelope, reason="publish_failed")

    async def _quarantine(self, envelope: EventEnvelope, *, reason: str) -> None:
        self._telemetry.record_dlq(envelope.event_type)
        if self._stream is not None and hasattr(self._stream, "quarantine"):
            await self._stream.quarantine(envelope, reason=reason)
        logger.warning(
            "event=live_bus_quarantine type=%s reason=%s correlation=%s",
            envelope.event_type,
            reason,
            envelope.correlation_id,
        )

    async def replay(self, *, limit: int = 100) -> int:
        if self._stream is not None and hasattr(self._stream, "replay_stream"):
            return await self._stream.replay_stream(limit=limit)
        if self._inprocess is not None and hasattr(self._inprocess, "replay"):
            return await self._inprocess.replay(limit=limit)
        return 0

    @property
    def pending_count(self) -> int:
        if self._stream is not None and hasattr(self._stream, "pending_count"):
            return int(self._stream.pending_count)
        return 0

    @property
    def dead_letter_count(self) -> int:
        if self._stream is not None and hasattr(self._stream, "dead_letter_count"):
            return int(self._stream.dead_letter_count)
        if self._inprocess is not None:
            return int(self._inprocess.dead_letter_count)
        return 0

    def snapshot(self) -> dict[str, Any]:
        return {
            "pending": self.pending_count,
            "dlq": self.dead_letter_count,
            "handlers": {k: len(v) for k, v in self._handlers.items()},
            "telemetry": self._telemetry.snapshot(),
        }
