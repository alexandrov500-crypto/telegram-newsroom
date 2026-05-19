from __future__ import annotations

import logging
from dataclasses import dataclass

from bot.operations.repository import OperationsRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LongRunHealthScore:
    score: float
    alerts: tuple[str, ...]
    memory_mb: float
    storage_rows: int
    replay_divergence: float


class LongRunHealthTracker:
    """Trend scoring for continuous staging uptime."""

    def __init__(self, repository: OperationsRepository) -> None:
        self._repo = repository

    def score(
        self,
        *,
        memory_mb: float,
        storage_rows: int,
        replay_divergence: float,
        open_contradictions: int,
        confidence_mean: float,
        mesh_health: float,
    ) -> LongRunHealthScore:
        alerts: list[str] = []
        score = 1.0
        if memory_mb > 1500:
            alerts.append("memory_growth")
            score -= 0.15
        if storage_rows > 500_000:
            alerts.append("storage_growth")
            score -= 0.1
        if replay_divergence > 0.15:
            alerts.append("replay_divergence")
            score -= 0.2
        if open_contradictions > 30:
            alerts.append("contradiction_accumulation")
            score -= 0.1
        series = self._repo.epistemic_longitudinal_series(limit=10)
        if len(series) >= 5:
            confs = [float(s.get("confidence_mean") or 0) for s in series[-5:]]
            if confs[-1] - confs[0] > 0.12:
                alerts.append("confidence_inflation")
                score -= 0.1
        if mesh_health < 0.6:
            alerts.append("federation_instability")
            score -= 0.15
        score = max(0.0, min(1.0, score))
        if score < 0.7 and alerts:
            self._repo.enqueue_alert(
                alert_key="longrun:health",
                category="info",
                title="Long-run health regression",
                priority=60,
                detail={"score": score, "alerts": alerts},
            )
        return LongRunHealthScore(
            score=round(score, 4),
            alerts=tuple(alerts),
            memory_mb=memory_mb,
            storage_rows=storage_rows,
            replay_divergence=replay_divergence,
        )
