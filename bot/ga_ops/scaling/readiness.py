from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ScalingReadinessEvaluator:
    """Forecast queue/worker/redis/db pressure."""

    def evaluate(
        self,
        *,
        queue_depth: int = 0,
        worker_stale: int = 0,
        worker_total: int = 0,
        publishes_hour: int = 0,
        max_publish_hour: int = 40,
        redis_enabled: bool = False,
        event_bus_pending: int = 0,
    ) -> dict[str, Any]:
        queue_risk = min(1.0, queue_depth / 800.0)
        worker_risk = worker_stale / max(worker_total, 1) if worker_total else 0.0
        publish_risk = min(1.0, publishes_hour / max(max_publish_hour, 1))
        bus_risk = min(1.0, event_bus_pending / 500.0)
        score = max(queue_risk, worker_risk, publish_risk, bus_risk)
        actions: list[str] = []
        if queue_risk > 0.6:
            actions.append("scale_ingest_worker")
        if worker_risk > 0.2:
            actions.append("restart_stale_workers")
        if publish_risk > 0.85:
            actions.append("throttle_publish_rate")
        if redis_enabled and bus_risk > 0.5:
            actions.append("monitor_redis_memory")
        return {
            "scaling_risk_score": round(score, 3),
            "recommended_actions": actions,
            "components": {
                "queue": queue_risk,
                "workers": worker_risk,
                "publish": publish_risk,
                "event_bus": bus_risk,
            },
        }
