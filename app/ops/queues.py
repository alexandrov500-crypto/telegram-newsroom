"""Priority queue abstraction (in-memory now; Redis/NATS-ready interface)."""

from __future__ import annotations

import asyncio
import os
from enum import Enum
from typing import Any, Protocol, runtime_checkable

from app.observability import ops_metrics as om


class Lane(str, Enum):
    FAST = "fast"
    STANDARD = "standard"
    SLOW = "slow"


@runtime_checkable
class PriorityQueue(Protocol):
    """Async lane queue contract for future Redis/NATS backends."""

    @property
    def name(self) -> str: ...

    @property
    def maxsize(self) -> int: ...

    def push_nowait(self, item: dict[str, Any]) -> bool: ...

    async def pop(self, *, timeout: float | None = 0.5) -> dict[str, Any] | None: ...

    def size(self) -> int: ...

    def task_done(self) -> None: ...


class InMemoryPriorityQueue:
    """Bounded asyncio.Queue wrapper."""

    def __init__(self, name: str, *, maxsize: int) -> None:
        self._name = name
        self._maxsize = max(1, maxsize)
        self._q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self._maxsize)

    @property
    def name(self) -> str:
        return self._name

    @property
    def maxsize(self) -> int:
        return self._maxsize

    @property
    def raw(self) -> asyncio.Queue[dict[str, Any]]:
        return self._q

    def push_nowait(self, item: dict[str, Any]) -> bool:
        try:
            self._q.put_nowait(item)
            return True
        except asyncio.QueueFull:
            om.record_overflow(self._name)
            return False

    async def pop(self, *, timeout: float | None = 0.5) -> dict[str, Any] | None:
        try:
            if timeout is None:
                return await self._q.get()
            return await asyncio.wait_for(self._q.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None
        except asyncio.CancelledError:
            raise

    def size(self) -> int:
        return self._q.qsize()

    def task_done(self) -> None:
        self._q.task_done()


class LaneQueueRegistry:
    def __init__(self, *, fast: InMemoryPriorityQueue, standard: InMemoryPriorityQueue, slow: InMemoryPriorityQueue) -> None:
        self.fast = fast
        self.standard = standard
        self.slow = slow

    def get(self, lane: Lane) -> InMemoryPriorityQueue:
        if lane == Lane.FAST:
            return self.fast
        if lane == Lane.STANDARD:
            return self.standard
        return self.slow

    def depths(self) -> dict[str, int]:
        return {
            "fast": self.fast.size(),
            "standard": self.standard.size(),
            "slow": self.slow.size(),
        }


_registry: LaneQueueRegistry | None = None


def init_lane_queues(
    *,
    fast_max: int | None = None,
    standard_max: int | None = None,
    slow_max: int | None = None,
) -> LaneQueueRegistry:
    global _registry
    _registry = LaneQueueRegistry(
        fast=InMemoryPriorityQueue("fast", maxsize=fast_max or int(os.getenv("LANE_QUEUE_FAST_MAX", "32"))),
        standard=InMemoryPriorityQueue(
            "standard",
            maxsize=standard_max or int(os.getenv("LANE_QUEUE_STANDARD_MAX", "512")),
        ),
        slow=InMemoryPriorityQueue("slow", maxsize=slow_max or int(os.getenv("LANE_QUEUE_SLOW_MAX", "1024"))),
    )
    return _registry


def get_lane_queues() -> LaneQueueRegistry | None:
    return _registry


def reset_lane_queues_for_tests() -> None:
    global _registry
    _registry = None


def sync_legacy_worker_queues() -> None:
    """Expose asyncio queues on app.worker.queues for backward compatibility."""
    reg = get_lane_queues()
    if reg is None:
        return
    from app.worker import queues as legacy

    legacy.breaking_queue = reg.fast.raw
    legacy.high_queue = reg.standard.raw
    legacy.normal_queue = reg.slow.raw
