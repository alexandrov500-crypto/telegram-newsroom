from __future__ import annotations

from dataclasses import dataclass

from bot.cognitive.repository import CognitiveRepository
from bot.cognitive.types import CognitiveContext, CognitivePolicyDocument


@dataclass(frozen=True)
class CostDecision:
    allow_generation: bool
    max_depth: str
    batch_size: int
    reason: str
    forecast_spend_usd: float


class CostIntelligence:
    """Economic orchestration for token spend and resource pressure."""

    def __init__(self, repository: CognitiveRepository, policy: CognitivePolicyDocument) -> None:
        self._repo = repository
        self._policy = policy

    def decide(self, ctx: CognitiveContext) -> CostDecision:
        budget = self._repo.get_budget_state()
        spend = budget["daily_spend_usd"]
        cap = budget["daily_budget_usd"] or float(self._policy.cost.get("daily_budget_usd", 25.0))
        ratio = spend / cap if cap > 0 else 0.0
        threshold = float(self._policy.cost.get("low_cost_mode_threshold", 0.9))

        if ratio >= 1.0:
            return CostDecision(False, "none", 0, "daily_budget_exceeded", spend)
        if ratio >= threshold:
            return CostDecision(True, "shallow", 1, "low_cost_degradation", spend + 0.01)
        if ctx.qos_class == "breaking":
            return CostDecision(True, "medium", 1, "breaking_priority", spend + 0.05)
        depth = "deep" if ctx.importance_score > 0.8 else "medium"
        batch = 4 if ctx.operation in ("digest", "backfill") else 1
        return CostDecision(True, depth, batch, "normal", spend + 0.02)

    def record_spend(self, usd: float) -> None:
        if usd <= 0:
            return
        self._repo.update_budget_spend(usd)
        try:
            from bot.observability.metrics import record_cognitive_spend

            record_cognitive_spend(usd)
        except Exception:
            pass

    def forecast_daily(self, *, hourly_rate_usd: float, hours_left: int = 12) -> float:
        budget = self._repo.get_budget_state()
        projected = budget["daily_spend_usd"] + hourly_rate_usd * hours_left
        return round(projected, 4)
