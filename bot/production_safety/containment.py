from __future__ import annotations

import asyncio
import logging
import sys
from dataclasses import dataclass
from typing import Any, Callable

from bot.production_safety.settings import ProductionSafetySettings
from bot.production_safety.types import ContainmentSnapshot

logger = logging.getLogger(__name__)


@dataclass
class RuntimeContainment:
    """Queue explosion, memory pressure, async starvation protections."""

    settings: ProductionSafetySettings
    ingest_throttle_factor: float = 1.0
    _dlq_depth_fn: Callable[[], int] | None = None

    def configure_dlq_fn(self, fn: Callable[[], int]) -> None:
        self._dlq_depth_fn = fn

    def assess(
        self,
        *,
        queue_depth: int,
        poison_count: int = 0,
        ingest_paused: bool = False,
    ) -> ContainmentSnapshot:
        stuck = self._count_long_running_tasks()
        memory_pressure = self._memory_pressure()
        throttled = queue_depth > self.settings.max_queue_depth
        if throttled:
            self.ingest_throttle_factor = max(0.25, 1.0 - queue_depth / 2000.0)
            logger.warning(
                "event=containment_throttle queue=%d factor=%.2f",
                queue_depth,
                self.ingest_throttle_factor,
            )
        else:
            self.ingest_throttle_factor = 1.0

        dlq = self._dlq_depth_fn() if self._dlq_depth_fn else 0
        return ContainmentSnapshot(
            queue_depth=queue_depth,
            throttled=throttled,
            ingest_paused=ingest_paused,
            memory_pressure=memory_pressure,
            stuck_tasks=stuck,
            dlq_depth=dlq,
            poison_count=poison_count,
        )

    def should_pause_ingest(self, snap: ContainmentSnapshot) -> bool:
        return snap.queue_depth > self.settings.max_queue_depth * 2 or snap.memory_pressure

    @staticmethod
    def _count_long_running_tasks() -> int:
        try:
            tasks = asyncio.all_tasks()
            return sum(1 for t in tasks if not t.done() and t.get_name().startswith("stalled-"))
        except Exception:
            return 0

    def _memory_pressure(self) -> bool:
        try:
            import resource

            usage = resource.getrusage(resource.RUSAGE_SELF)
            rss_mb = usage.ru_maxrss / (1024 * 1024) if sys.platform == "darwin" else usage.ru_maxrss / 1024
            return rss_mb > self.settings.memory_rss_warn_mb
        except Exception:
            return False

    def check_task_cardinality(self) -> bool:
        try:
            count = len(asyncio.all_tasks())
            if count > self.settings.max_async_tasks:
                logger.error("event=task_cardinality_exceeded count=%d", count)
                return False
        except Exception:
            pass
        return True
