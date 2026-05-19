from __future__ import annotations

import logging
import sys
import time
from collections import deque
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class StabilitySample:
    at_monotonic: float
    memory_mb: float
    queue_depth: int
    event_loop_lag_ms: float
    token_spend_hour: float


@dataclass
class LongRunStabilityTracker:
    """Multi-day uptime: trends, drift, rolling stability score."""

    _samples: deque[StabilitySample] = field(default_factory=lambda: deque(maxlen=288))
    _task_counts: deque[int] = field(default_factory=lambda: deque(maxlen=48))

    def record(
        self,
        *,
        queue_depth: int,
        event_loop_lag_ms: float = 0.0,
        token_spend_hour: float = 0.0,
    ) -> float:
        mem = self._rss_mb()
        self._samples.append(
            StabilitySample(
                at_monotonic=time.monotonic(),
                memory_mb=mem,
                queue_depth=queue_depth,
                event_loop_lag_ms=event_loop_lag_ms,
                token_spend_hour=token_spend_hour,
            ),
        )
        try:
            import asyncio

            self._task_counts.append(len(asyncio.all_tasks()))
        except Exception:
            self._task_counts.append(0)
        score = self.rolling_score()
        try:
            from bot.observability.metrics import set_long_run_stability_score

            set_long_run_stability_score(score)
        except Exception:
            pass
        return score

    def rolling_score(self) -> float:
        if not self._samples:
            return 1.0
        latest = self._samples[-1]
        score = 1.0
        if latest.queue_depth > 400:
            score -= 0.2
        if latest.event_loop_lag_ms > 500:
            score -= 0.25
        if latest.memory_mb > 2500:
            score -= 0.15
        if len(self._samples) >= 10:
            q0 = self._samples[0].queue_depth
            q1 = latest.queue_depth
            hours = max((latest.at_monotonic - self._samples[0].at_monotonic) / 3600, 0.1)
            growth = (q1 - q0) / hours
            if growth > 100:
                score -= 0.2
                logger.warning("event=queue_growth_drift rate=%.1f/h", growth)
        if self._task_counts and max(self._task_counts) > 450:
            score -= 0.1
        return max(0.0, min(1.0, score))

    def drift_forecast(self) -> str:
        score = self.rolling_score()
        if score >= 0.85:
            return "stable"
        if score >= 0.65:
            return "watch"
        return "degrading"

    @staticmethod
    def _rss_mb() -> float:
        try:
            import resource

            u = resource.getrusage(resource.RUSAGE_SELF)
            if sys.platform == "darwin":
                return u.ru_maxrss / (1024 * 1024)
            return u.ru_maxrss / 1024
        except Exception:
            return 0.0
