from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from bot.rc1.repository import Rc1Repository

logger = logging.getLogger(__name__)

_BASELINE_METRICS = (
    "queue_depth",
    "cognition_latency_sec",
    "telegram_latency_sec",
    "publish_rate_hour",
    "retry_rate",
    "budget_usd_hour",
    "operator_actions_hour",
)


@dataclass
class BaselineEngine:
    """Learn normal behavior; score anomalies vs baseline."""

    repository: Rc1Repository
    z_threshold: float = 2.5

    def ingest(
        self,
        *,
        queue_depth: int = 0,
        cognition_sec: float | None = None,
        telegram_sec: float | None = None,
        publish_rate: float = 0.0,
        retry_rate: float = 0.0,
        budget_hour: float = 0.0,
        operator_actions: float = 0.0,
    ) -> None:
        self.repository.update_baseline("queue_depth", float(queue_depth))
        if cognition_sec is not None:
            self.repository.update_baseline("cognition_latency_sec", cognition_sec)
        if telegram_sec is not None:
            self.repository.update_baseline("telegram_latency_sec", telegram_sec)
        self.repository.update_baseline("publish_rate_hour", publish_rate)
        self.repository.update_baseline("retry_rate", retry_rate)
        self.repository.update_baseline("budget_usd_hour", budget_hour)
        self.repository.update_baseline("operator_actions_hour", operator_actions)

    def deviation_score(self, metric: str, value: float) -> float:
        base = self.repository.get_baseline(metric)
        if base is None:
            return 0.0
        mean, std = base
        if std < 1e-6:
            return 0.0 if abs(value - mean) < 1e-3 else 1.0
        z = abs(value - mean) / std
        return min(1.0, z / self.z_threshold)

    def anomaly_report(self, current: dict[str, float]) -> dict[str, Any]:
        alerts: list[str] = []
        scores: dict[str, float] = {}
        for metric in _BASELINE_METRICS:
            if metric not in current:
                continue
            dev = self.deviation_score(metric, current[metric])
            scores[metric] = dev
            if dev >= 1.0:
                alerts.append(metric)
                logger.warning("event=baseline_anomaly metric=%s dev=%.2f", metric, dev)
        return {
            "alerts": alerts,
            "deviations": scores,
            "unusual": len(alerts) > 0,
        }
