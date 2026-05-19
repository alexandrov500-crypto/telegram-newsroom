from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any

from bot.events.types import NewsroomEvent

EventHandler = Callable[[NewsroomEvent], Awaitable[None]]


class DistributedEventBus(ABC):
    """Pluggable distributed event bus."""

    backend_name: str = "abstract"

    @abstractmethod
    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        ...

    @abstractmethod
    def subscribe_all(self, handler: EventHandler) -> None:
        ...

    @abstractmethod
    async def publish(self, event: NewsroomEvent, *, topic: str | None = None) -> bool:
        ...

    @abstractmethod
    async def replay(self, *, limit: int = 100) -> int:
        ...

    @abstractmethod
    def start(self) -> Any:
        ...

    @abstractmethod
    async def stop(self) -> None:
        ...

    @property
    @abstractmethod
    def dead_letter_count(self) -> int:
        ...

    @property
    @abstractmethod
    def dropped_count(self) -> int:
        ...
