from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from typing import Any

from bot.distributed.event_bus.base import DistributedEventBus, EventHandler
from bot.distributed.event_bus.security import sign_event_payload, verify_event_payload
from bot.events.types import NewsroomEvent

logger = logging.getLogger(__name__)

_CHANNEL_PREFIX = "newsroom:events:"


class RedisDistributedBus(DistributedEventBus):
    """Redis pub/sub fanout with local dispatch queue."""

    backend_name = "redis"

    def __init__(
        self,
        redis_client: Any,
        *,
        node_id: str,
        store: Any | None = None,
        max_queue: int = 5000,
    ) -> None:
        self._redis = redis_client
        self._node_id = node_id
        self._store = store
        self._handlers: dict[str, list[EventHandler]] = {}
        self._wildcard: list[EventHandler] = []
        self._queue: asyncio.Queue[NewsroomEvent | None] = asyncio.Queue(maxsize=max_queue)
        self._dlq: deque[NewsroomEvent] = deque(maxlen=500)
        self._dropped = 0
        self._pubsub = None
        self._listener_task: asyncio.Task[None] | None = None
        self._worker_task: asyncio.Task[None] | None = None
        self._running = False
        self._seen_ids: deque[str] = deque(maxlen=10_000)

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    def subscribe_all(self, handler: EventHandler) -> None:
        self._wildcard.append(handler)

    async def publish(self, event: NewsroomEvent, *, topic: str | None = None) -> bool:
        channel = _CHANNEL_PREFIX + (topic or event.event_type)
        payload = sign_event_payload(event.to_dict())
        if self._store is not None:
            try:
                self._store.append(event)
            except Exception:
                logger.exception("event=redis_bus_store_failed")
        try:
            await self._redis.publish(channel, json.dumps(payload))
            from bot.observability.metrics import record_distributed_event

            record_distributed_event(backend="redis", event_type=event.event_type)
            return True
        except Exception:
            logger.exception("event=redis_publish_failed channel=%s", channel)
            self._dropped += 1
            self._dlq.append(event)
            return False

    async def replay(self, *, limit: int = 100) -> int:
        if self._store is None:
            return 0
        count = 0
        for event in self._store.recent_unprocessed(limit=limit):
            await self._enqueue_local(event)
            count += 1
        return count

    async def _enqueue_local(self, event: NewsroomEvent) -> None:
        if event.event_id in self._seen_ids:
            return
        try:
            self._queue.put_nowait(event)
            self._seen_ids.append(event.event_id)
        except asyncio.QueueFull:
            self._dropped += 1
            self._dlq.append(event)

    async def _listener(self) -> None:
        assert self._pubsub is not None
        while self._running:
            try:
                message = await self._pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=1.0,
                )
                if message is None or message.get("type") != "message":
                    await asyncio.sleep(0.01)
                    continue
                data = message.get("data")
                if isinstance(data, bytes):
                    data = data.decode("utf-8")
                raw = json.loads(data)
                payload = dict(raw.get("payload") or raw)
                if not verify_event_payload(payload):
                    logger.warning("event=redis_bus_sig_invalid")
                    continue
                event = NewsroomEvent.from_dict(raw if "event_type" in raw else payload)
                await self._enqueue_local(event)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("event=redis_listener_failed")
                await asyncio.sleep(0.5)

    async def _worker(self) -> None:
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            if event is None:
                break
            handlers = list(self._wildcard)
            handlers.extend(self._handlers.get(event.event_type, []))
            for handler in handlers:
                try:
                    await handler(event)
                except Exception:
                    logger.exception("event=redis_bus_handler_failed type=%s", event.event_type)
            if self._store is not None:
                try:
                    self._store.mark_processed(event.event_id)
                except Exception:
                    pass
            self._queue.task_done()

    def start(self) -> asyncio.Task[None]:
        if self._running:
            return self._worker_task  # type: ignore[return-value]
        self._running = True
        self._pubsub = self._redis.pubsub()
        self._pubsub.psubscribe(_CHANNEL_PREFIX + "*")
        self._listener_task = asyncio.create_task(self._listener(), name="redis-bus-listener")
        self._worker_task = asyncio.create_task(self._worker(), name="redis-bus-worker")
        return self._worker_task

    async def stop(self) -> None:
        self._running = False
        try:
            self._queue.put_nowait(None)
        except asyncio.QueueFull:
            pass
        for task in (self._listener_task, self._worker_task):
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        if self._pubsub is not None:
            await self._pubsub.close()

    @property
    def dead_letter_count(self) -> int:
        return len(self._dlq)

    @property
    def dropped_count(self) -> int:
        return self._dropped
