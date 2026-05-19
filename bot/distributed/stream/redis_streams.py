from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from typing import Any

from bot.distributed.stream.base import StreamEventBus, StreamHandler
from bot.events.envelope import EventEnvelope
from bot.events.validation import is_poison_message, validate_envelope

logger = logging.getLogger(__name__)

_STREAM_PREFIX = "newsroom:stream:"
_GROUP_PREFIX = "newsroom:cg:"
_DEFAULT_MAXLEN = 100_000


class RedisStreamsBus(StreamEventBus):
    """Redis Streams with consumer groups, acks, and retention."""

    backend_name = "redis_streams"

    def __init__(
        self,
        redis_client: Any,
        *,
        node_id: str,
        consumer_group: str | None = None,
        sourced_store: Any | None = None,
        max_len: int = _DEFAULT_MAXLEN,
    ) -> None:
        self._redis = redis_client
        self._node_id = node_id
        self._group = consumer_group or f"newsroom-{node_id}"
        self._consumer = f"{node_id}-consumer"
        self._sourced = sourced_store
        self._max_len = max_len
        self._handlers: dict[str, list] = {}
        self._envelope_handlers: dict[str, list[StreamHandler]] = {}
        self._wildcard_env: list[StreamHandler] = []
        self._dlq: deque[EventEnvelope] = deque(maxlen=500)
        self._pending: dict[str, tuple[str, str]] = {}
        self._worker_task: asyncio.Task[None] | None = None
        self._running = False
        self._dropped = 0

    def _stream_key(self, partition: str) -> str:
        return f"{_STREAM_PREFIX}{partition}"

    async def _ensure_group(self, stream_key: str) -> None:
        try:
            await self._redis.xgroup_create(
                stream_key,
                self._group,
                id="0",
                mkstream=True,
            )
        except Exception as exc:
            if "BUSYGROUP" not in str(exc):
                logger.debug("event=xgroup_create_skipped stream=%s err=%s", stream_key, exc)

    def subscribe(self, event_type: str, handler) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    def subscribe_all(self, handler) -> None:
        self._handlers.setdefault("*", []).append(handler)

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
        partition = topic or envelope.partition_key
        stream_key = self._stream_key(partition)
        body = envelope.to_json(sign=True)
        if self._sourced is not None:
            self._sourced.append(envelope)
        try:
            msg_id = await self._redis.xadd(
                stream_key,
                {"envelope": body},
                maxlen=self._max_len,
                approximate=True,
            )
            mid = msg_id.decode() if isinstance(msg_id, bytes) else str(msg_id)
            from bot.observability.metrics import record_distributed_event, record_stream_publish

            record_distributed_event(backend="redis_streams", event_type=envelope.event_type)
            record_stream_publish(partition)
            return mid
        except Exception:
            logger.exception("event=redis_stream_publish_failed")
            self._dropped += 1
            self._dlq.append(envelope)
            return None

    async def publish(self, event, *, topic: str | None = None) -> bool:
        from bot.distributed.config import load_cluster_config

        cfg = load_cluster_config()
        envelope = EventEnvelope.from_legacy_event(
            event,
            node_id=cfg.node_id,
            region=cfg.node_region,
        )
        return (await self.publish_envelope(envelope, topic=topic)) is not None

    async def ack(self, stream_key: str, message_id: str) -> bool:
        try:
            await self._redis.xack(stream_key, self._group, message_id)
            pending = self._pending.pop(message_id, None)
            if pending and self._sourced is not None:
                _, event_id = pending
                self._sourced.mark_processed(event_id)
            return True
        except Exception:
            logger.exception("event=redis_stream_ack_failed id=%s", message_id)
            return False

    async def _consume_loop(self) -> None:
        streams = [self._stream_key("global")]
        for key in streams:
            await self._ensure_group(key)
        while self._running:
            try:
                results = await self._redis.xreadgroup(
                    self._group,
                    self._consumer,
                    {k: ">" for k in streams},
                    count=10,
                    block=2000,
                )
                if not results:
                    await asyncio.sleep(0.05)
                    continue
                for stream_key_raw, messages in results:
                    stream_key = (
                        stream_key_raw.decode()
                        if isinstance(stream_key_raw, bytes)
                        else str(stream_key_raw)
                    )
                    for msg_id_raw, fields in messages:
                        msg_id = msg_id_raw.decode() if isinstance(msg_id_raw, bytes) else str(msg_id_raw)
                        raw = fields.get(b"envelope") or fields.get("envelope")
                        if raw is None:
                            continue
                        if isinstance(raw, bytes):
                            raw = raw.decode("utf-8")
                        try:
                            envelope = EventEnvelope.from_json(raw)
                        except Exception:
                            logger.exception("event=stream_envelope_parse_failed")
                            await self._redis.xack(stream_key, self._group, msg_id)
                            continue
                        self._pending[msg_id] = (stream_key, envelope.event_id)
                        await self._dispatch_envelope(stream_key, msg_id, envelope)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("event=redis_stream_consume_failed")
                await asyncio.sleep(1.0)

    async def _dispatch_envelope(
        self,
        stream_key: str,
        msg_id: str,
        envelope: EventEnvelope,
    ) -> None:
        legacy = envelope.to_legacy_event()
        handlers = list(self._handlers.get(envelope.event_type, []))
        handlers.extend(self._handlers.get("*", []))
        try:
            for handler in self._envelope_handlers.get(envelope.event_type, []):
                await handler(envelope)
            for handler in handlers:
                await handler(legacy)
            await self.ack(stream_key, msg_id)
        except Exception:
            logger.exception("event=stream_dispatch_failed type=%s", envelope.event_type)
            retried = envelope.with_retry()
            self._dlq.append(retried)
            if is_poison_message(retried):
                await self.quarantine(envelope, reason="handler_failures")
                await self.ack(stream_key, msg_id)

    async def replay_stream(
        self,
        *,
        stream_key: str | None = None,
        from_id: str = "0",
        limit: int = 100,
    ) -> int:
        key = stream_key or self._stream_key("global")
        entries = await self._redis.xrange(key, min=from_id, max="+", count=limit)
        count = 0
        for msg_id_raw, fields in entries:
            raw = fields.get(b"envelope") or fields.get("envelope")
            if raw is None:
                continue
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            envelope = EventEnvelope.from_json(raw, verify_signature=False)
            await self.publish_envelope(envelope)
            count += 1
        return count

    async def quarantine(self, envelope: EventEnvelope, *, reason: str) -> None:
        if self._sourced is not None:
            self._sourced.quarantine(envelope.event_id, reason=reason)
        self._dlq.append(envelope)
        try:
            from bot.observability.metrics import record_stream_quarantine

            record_stream_quarantine(envelope.event_type)
        except Exception:
            pass

    async def replay(self, *, limit: int = 100) -> int:
        if self._sourced is not None:
            envelopes = self._sourced.replay_range(limit=limit)
            for env in envelopes:
                await self.publish_envelope(env)
            return len(envelopes)
        return await self.replay_stream(limit=limit)

    def start(self) -> asyncio.Task[None]:
        if self._running:
            return self._worker_task  # type: ignore[return-value]
        self._running = True
        self._worker_task = asyncio.create_task(
            self._consume_loop(),
            name="redis-streams-consumer",
        )
        return self._worker_task

    async def stop(self) -> None:
        self._running = False
        if self._worker_task is not None:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    @property
    def dead_letter_count(self) -> int:
        return len(self._dlq)

    @property
    def dropped_count(self) -> int:
        return self._dropped

    @property
    def pending_count(self) -> int:
        return len(self._pending)
