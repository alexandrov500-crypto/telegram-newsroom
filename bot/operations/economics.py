from __future__ import annotations

from dataclasses import dataclass

from bot.operations.repository import OperationsRepository
from bot.operations.types import ProductionSLOs


@dataclass(frozen=True)
class CostAttribution:
    region: str | None
    token_spend_usd: float
    replay_cost_usd: float
    cognition_cost_usd: float
    federation_cost_usd: float
    total_usd: float
    anomaly: bool
    explanation: str


class ProductionEconomics:
    """Production cost tracking and throttling signals."""

    def __init__(self, repository: OperationsRepository, slos: ProductionSLOs | None = None) -> None:
        self._repo = repository
        self._slos = slos or ProductionSLOs()

    def record(
        self,
        *,
        region: str | None,
        token_spend: float = 0.0,
        replay_cost: float = 0.0,
        cognition_cost: float = 0.0,
        federation_cost: float = 0.0,
    ) -> CostAttribution:
        total = token_spend + replay_cost + cognition_cost + federation_cost
        anomaly_score = 0.0
        if total > self._slos.openai_daily_budget_usd * 0.9:
            anomaly_score = min(1.0, total / self._slos.openai_daily_budget_usd)
        self._repo.record_cost_snapshot(
            region=region,
            token_spend=token_spend,
            replay_cost=replay_cost,
            cognition_cost=cognition_cost,
            federation_cost=federation_cost,
            anomaly=anomaly_score,
        )
        try:
            from bot.observability.metrics import record_ops_cost

            record_ops_cost(total, region or "global")
        except Exception:
            pass
        return CostAttribution(
            region=region,
            token_spend_usd=token_spend,
            replay_cost_usd=replay_cost,
            cognition_cost_usd=cognition_cost,
            federation_cost_usd=federation_cost,
            total_usd=total,
            anomaly=anomaly_score > 0.85,
            explanation=f"total=${total:.2f} anomaly={anomaly_score:.2f}",
        )

    def recommend_mode(self, total_daily: float) -> str:
        budget = self._slos.openai_daily_budget_usd
        if total_daily >= budget:
            return "low_cost_operational"
        if total_daily >= budget * 0.85:
            return "cognition_throttle"
        return "normal"
