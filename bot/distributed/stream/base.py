from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any

from bot.distributed.event_bus.base import DistributedEventBus, EventHandler
from bot.events.envelope import EventEnvelope

StreamHandler = Callable[[EventEnvelope], Awaitable[None]]


class StreamEventBus(DistributedEventBus, ABC):
    """Durable stream semantics: consumer groups, acks, replay, DLQ."""

    @abstractmethod
    async def publish_envelope(
        self,
        envelope: EventEnvelope,
        *,
        topic: str | None = None,
    ) -> str | None:
        """Publish envelope; return stream message id if durable."""

    @abstractmethod
    async def ack(self, stream_key: str, message_id: str) -> bool:
        ...

    @abstractmethod
    def subscribe_envelope(self, event_type: str, handler: StreamHandler) -> None:
        ...

    @abstractmethod
    async def replay_stream(
        self,
        *,
        stream_key: str | None = None,
        from_id: str = "0",
        limit: int = 100,
    ) -> int:
        ...

    @abstractmethod
    async def quarantine(self, envelope: EventEnvelope, *, reason: str) -> None:
        ...

    @property
    @abstractmethod
    def pending_count(self) -> int:
        ...
