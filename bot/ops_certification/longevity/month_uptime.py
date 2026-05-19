from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class LongevityProtector:
    """Month-long uptime: aging, drift, compaction signals."""

    _memory_samples: deque[float] = field(default_factory=lambda: deque(maxlen=336))
    _retry_samples: deque[int] = field(default_factory=lambda: deque(maxlen=96))
    _task_ages: deque[float] = field(default_factory=lambda: deque(maxlen=48))

    def record_memory_mb(self, mb: float) -> None:
        self._memory_samples.append(mb)

    def record_retry_burst(self, count: int) -> None:
        self._retry_samples.append(count)

    def record_task_age(self, age_sec: float) -> None:
        self._task_ages.append(age_sec)

    def fragmentation_risk(self) -> float:
        if len(self._memory_samples) < 10:
            return 0.0
        vals = list(self._memory_samples)
        growth = (vals[-1] - vals[0]) / max(len(vals), 1)
        return min(1.0, max(0.0, growth / 500.0))

    def retry_amplification_risk(self) -> float:
        if not self._retry_samples:
            return 0.0
        recent = list(self._retry_samples)[-12:]
        if max(recent) > 100 and sum(recent) / len(recent) > 30:
            return 0.8
        return 0.1

    def runtime_aging_score(self) -> float:
        frag = self.fragmentation_risk()
        retry = self.retry_amplification_risk()
        score = 1.0 - frag * 0.4 - retry * 0.4
        try:
            from bot.observability.metrics import set_runtime_aging_score

            set_runtime_aging_score(score)
        except Exception:
            pass
        return max(0.0, min(1.0, score))

    def degradation_forecast(self) -> str:
        aging = self.runtime_aging_score()
        if aging >= 0.85:
            return "healthy"
        if aging >= 0.65:
            return "aging_watch"
        return "degradation_likely"

    def maintenance_recommendations(self) -> list[str]:
        recs: list[str] = []
        if self.fragmentation_risk() > 0.3:
            recs.append("schedule_memory_maintenance_restart")
        if self.retry_amplification_risk() > 0.5:
            recs.append("trim_retry_queues")
        if self._task_ages and max(self._task_ages) > 3600:
            recs.append("orphan_task_cleanup")
        recs.append("event_stream_trim_if_redis_enabled")
        return recs

    def tick(self, *, memory_mb: float, queue_depth: int) -> dict[str, float | str]:
        self.record_memory_mb(memory_mb)
        self.record_retry_burst(queue_depth // 10)
        return {
            "aging_score": self.runtime_aging_score(),
            "forecast": self.degradation_forecast(),
            "fragmentation_risk": self.fragmentation_risk(),
        }
