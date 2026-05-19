from __future__ import annotations

from typing import Any

from bot.distributed.event_bus.base import DistributedEventBus, EventHandler
from bot.distributed.event_bus.security import sign_event_payload
from bot.events.bus import EventBus
from bot.events.types import NewsroomEvent


class InMemoryDistributedBus(DistributedEventBus):
    """Local asyncio bus (single-node / dev)."""

    backend_name = "inmemory"

    def __init__(self, *, store: Any | None = None, max_queue: int = 2000) -> None:
        self._inner = EventBus(store=store, max_queue=max_queue)

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        self._inner.subscribe(event_type, handler)

    def subscribe_all(self, handler: EventHandler) -> None:
        self._inner.subscribe_all(handler)

    async def publish(self, event: NewsroomEvent, *, topic: str | None = None) -> bool:
        _ = topic
        signed = NewsroomEvent(
            event_id=event.event_id,
            event_type=event.event_type,
            created_at=event.created_at,
            payload=sign_event_payload(dict(event.payload)),
        )
        ok = await self._inner.publish(signed)
        if ok:
            try:
                from bot.observability.metrics import record_distributed_event

                record_distributed_event(backend="inmemory", event_type=event.event_type)
            except Exception:
                pass
        return ok

    async def replay(self, *, limit: int = 100) -> int:
        return await self._inner.replay(limit=limit)

    def start(self) -> Any:
        return self._inner.start()

    async def stop(self) -> None:
        await self._inner.stop()

    @property
    def dead_letter_count(self) -> int:
        return self._inner.dead_letter_count

    @property
    def dropped_count(self) -> int:
        return self._inner.dropped_count
