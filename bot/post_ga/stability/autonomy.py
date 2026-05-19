from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from bot.post_ga.repository import PostGaRepository


@dataclass
class AutonomyStabilizer:
    """Multi-week uptime: fatigue, rejuvenation, drift normalization."""

    repository: PostGaRepository
    _retry_bursts: deque[int] = field(default_factory=lambda: deque(maxlen=24))
    _memory_samples: deque[float] = field(default_factory=lambda: deque(maxlen=48))
    _queue_samples: deque[int] = field(default_factory=lambda: deque(maxlen=48))

    def observe(
        self,
        *,
        queue_depth: int,
        retry_count: int = 0,
        memory_mb: float = 0.0,
        task_count: int = 0,
    ) -> dict[str, Any]:
        self._queue_samples.append(queue_depth)
        self._retry_bursts.append(retry_count)
        if memory_mb > 0:
            self._memory_samples.append(memory_mb)

        retry_fatigue = sum(self._retry_bursts) / max(len(self._retry_bursts), 1)
        q_growth = 0.0
        if len(self._queue_samples) >= 10:
            q_growth = (self._queue_samples[-1] - self._queue_samples[0]) / len(self._queue_samples)

        fatigue_index = min(1.0, retry_fatigue / 50.0 + max(0, q_growth) / 200.0)
        autonomy_score = max(0.0, 1.0 - fatigue_index * 0.6)
        if self._memory_samples and max(self._memory_samples) > 2000:
            autonomy_score -= 0.1

        recs: list[str] = []
        if fatigue_index > 0.5:
            recs.append("schedule_worker_rejuvenation")
        if retry_fatigue > 30:
            recs.append("suppress_retry_amplification")
        if q_growth > 50:
            recs.append("queue_compaction_pass")
        if task_count > 400:
            recs.append("rolling_restart_advisory")

        detail = {
            "retry_fatigue": round(retry_fatigue, 1),
            "queue_growth": round(q_growth, 1),
            "recommendations": recs,
        }
        self.repository.save_stability(
            autonomy_score=autonomy_score,
            fatigue_index=fatigue_index,
            detail=detail,
        )
        return {
            "autonomy_stability_score": round(autonomy_score, 3),
            "runtime_fatigue_index": round(fatigue_index, 3),
            "recommendations": recs,
        }
