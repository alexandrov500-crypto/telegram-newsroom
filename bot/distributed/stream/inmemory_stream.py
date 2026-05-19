from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import Any

from bot.distributed.event_bus.inmemory import InMemoryDistributedBus
from bot.distributed.stream.base import StreamEventBus, StreamHandler
from bot.events.envelope import EventEnvelope
from bot.events.validation import is_poison_message, validate_envelope

logger = logging.getLogger(__name__)


class InMemoryStreamBus(StreamEventBus):
    """Dev/test durable-stream semantics over in-memory dispatch."""

    backend_name = "inmemory_stream"

    def __init__(self, *, store: Any | None = None, sourced_store: Any | None = None) -> None:
        self._inner = InMemoryDistributedBus(store=store)
        self._sourced = sourced_store
        self._stream: deque[tuple[str, EventEnvelope]] = deque(maxlen=50_000)
        self._pending: dict[str, EventEnvelope] = {}
        self._envelope_handlers: dict[str, list[StreamHandler]] = {}
        self._wildcard_handlers: list[StreamHandler] = []
        self._dlq: deque[EventEnvelope] = deque(maxlen=500)
        self._msg_seq = 0

    def subscribe(self, event_type: str, handler) -> None:
        self._inner.subscribe(event_type, handler)

    def subscribe_all(self, handler) -> None:
        self._inner.subscribe_all(handler)

    def subscribe_envelope(self, event_type: str, handler: StreamHandler) -> None:
        self._envelope_handlers.setdefault(event_type, []).append(handler)

    async def publish_envelope(
        self,
        envelope: EventEnvelope,
        *,
        topic: str | None = None,
    ) -> str | None:
        validate_envelope(envelope)
        if is_poison_message(envelope):
            await self.quarantine(envelope, reason="max_retries_exceeded")
            return None
        self._msg_seq += 1
        msg_id = f"{self._msg_seq}"
        if self._sourced is not None:
            self._sourced.append(envelope)
        self._stream.append((msg_id, envelope))
        self._pending[msg_id] = envelope
        legacy = envelope.to_legacy_event()
        await self._inner.publish(legacy, topic=topic)
        for handler in self._wildcard_handlers:
            await self._dispatch(handler, envelope, msg_id)
        for handler in self._envelope_handlers.get(envelope.event_type, []):
            await self._dispatch(handler, envelope, msg_id)
        return msg_id

    async def publish(self, event, *, topic: str | None = None) -> bool:
        from bot.distributed.config import load_cluster_config

        cfg = load_cluster_config()
        envelope = EventEnvelope.from_legacy_event(
            event,
            node_id=cfg.node_id,
            region=cfg.node_region,
        )
        return (await self.publish_envelope(envelope, topic=topic)) is not None

    async def _dispatch(self, handler: StreamHandler, envelope: EventEnvelope, msg_id: str) -> None:
        try:
            await handler(envelope)
            await self.ack("memory", msg_id)
        except Exception:
            logger.exception("event=stream_handler_failed type=%s", envelope.event_type)
            self._dlq.append(envelope.with_retry())

    async def ack(self, stream_key: str, message_id: str) -> bool:
        env = self._pending.pop(message_id, None)
        if env and self._sourced is not None:
            self._sourced.mark_processed(env.event_id)
        return message_id in self._stream or env is not None

    async def replay_stream(
        self,
        *,
        stream_key: str | None = None,
        from_id: str = "0",
        limit: int = 100,
    ) -> int:
        _ = stream_key
        start = int(from_id) if from_id.isdigit() else 0
        count = 0
        for msg_id, envelope in list(self._stream):
            if int(msg_id) < start:
                continue
            await self.publish_envelope(envelope)
            count += 1
            if count >= limit:
                break
        return count

    async def quarantine(self, envelope: EventEnvelope, *, reason: str) -> None:
        if self._sourced is not None:
            self._sourced.quarantine(envelope.event_id, reason=reason)
        self._dlq.append(envelope)

    async def replay(self, *, limit: int = 100) -> int:
        if self._sourced is not None:
            envelopes = self._sourced.replay_range(limit=limit)
            for env in envelopes:
                await self.publish_envelope(env)
            return len(envelopes)
        return await self._inner.replay(limit=limit)

    def start(self) -> Any:
        return self._inner.start()

    async def stop(self) -> None:
        await self._inner.stop()

    @property
    def dead_letter_count(self) -> int:
        return len(self._dlq) + self._inner.dead_letter_count

    @property
    def dropped_count(self) -> int:
        return self._inner.dropped_count

    @property
    def pending_count(self) -> int:
        return len(self._pending)
