from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any

from bot.events.types import NewsroomEvent

logger = logging.getLogger(__name__)

EventHandler = Callable[[NewsroomEvent], Awaitable[None]]


class EventBus:
    """Async pub/sub with bounded queue, dead-letter buffer, and optional persistence."""

    def __init__(
        self,
        *,
        max_queue: int = 2000,
        dead_letter_capacity: int = 200,
        store: Any | None = None,
    ) -> None:
        self._queue: asyncio.Queue[NewsroomEvent | None] = asyncio.Queue(maxsize=max_queue)
        self._handlers: dict[str, list[EventHandler]] = {}
        self._wildcard_handlers: list[EventHandler] = []
        self._dlq: deque[NewsroomEvent] = deque(maxlen=dead_letter_capacity)
        self._store = store
        self._worker_task: asyncio.Task[None] | None = None
        self._running = False
        self._dropped = 0

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    def subscribe_all(self, handler: EventHandler) -> None:
        self._wildcard_handlers.append(handler)

    @property
    def dead_letter_count(self) -> int:
        return len(self._dlq)

    @property
    def dropped_count(self) -> int:
        return self._dropped

    async def publish(self, event: NewsroomEvent) -> bool:
        if self._store is not None:
            try:
                self._store.append(event)
            except Exception:
                logger.exception("event=event_store_append_failed type=%s", event.event_type)

        try:
            self._queue.put_nowait(event)
            return True
        except asyncio.QueueFull:
            self._dropped += 1
            self._dlq.append(event)
            try:
                from bot.observability.metrics import record_event_bus_dropped

                record_event_bus_dropped()
            except Exception:
                pass
            logger.warning(
                "event=event_bus_backpressure type=%s dropped_total=%d",
                event.event_type,
                self._dropped,
            )
            return False

    async def replay(self, *, limit: int = 100) -> int:
        if self._store is None:
            return 0
        count = 0
        for event in self._store.recent_unprocessed(limit=limit):
            await self.publish(event)
            count += 1
        return count

    async def _dispatch(self, event: NewsroomEvent) -> None:
        handlers = list(self._wildcard_handlers)
        handlers.extend(self._handlers.get(event.event_type, []))
        handlers.extend(self._handlers.get("*", []))

        for handler in handlers:
            try:
                await handler(event)
            except Exception:
                logger.exception(
                    "event=event_handler_failed type=%s handler=%s",
                    event.event_type,
                    getattr(handler, "__name__", repr(handler)),
                )

        if self._store is not None:
            try:
                self._store.mark_processed(event.event_id)
            except Exception:
                logger.exception("event=event_store_mark_failed id=%s", event.event_id)

    async def _worker(self) -> None:
        while self._running:
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            if event is None:
                break
            try:
                await self._dispatch(event)
            except Exception:
                logger.exception("event=event_dispatch_failed type=%s", event.event_type)
                self._dlq.append(event)
            finally:
                self._queue.task_done()

    def start(self) -> asyncio.Task[None]:
        if self._worker_task is not None and not self._worker_task.done():
            return self._worker_task
        self._running = True
        self._worker_task = asyncio.create_task(self._worker(), name="newsroom-event-bus")
        return self._worker_task

    async def stop(self) -> None:
        self._running = False
        try:
            self._queue.put_nowait(None)
        except asyncio.QueueFull:
            pass
        if self._worker_task is not None:
            try:
                await asyncio.wait_for(self._worker_task, timeout=5.0)
            except asyncio.TimeoutError:
                self._worker_task.cancel()

    def snapshot_dlq(self, *, limit: int = 20) -> list[dict[str, Any]]:
        return [event.to_dict() for event in list(self._dlq)[-limit:]]
