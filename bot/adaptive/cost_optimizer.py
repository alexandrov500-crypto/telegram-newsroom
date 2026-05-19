from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from bot.adaptive.policies import PolicyBundle
from bot.storage.observability_repository import ObservabilityRepository


@dataclass(frozen=True)
class AIBudgetDecision:
    allow_llm: bool
    model_tier: str
    reason: str
    skip_translation: bool = False
    skip_embeddings: bool = False


class CostOptimizer:
    """Cost-aware AI orchestration with daily budget caps."""

    CHEAP_MODEL = "gpt-4o-mini"
    STANDARD_MODEL = "gpt-4o"

    def __init__(
        self,
        obs_repo: ObservabilityRepository | None,
        *,
        policy: PolicyBundle,
    ) -> None:
        self._obs = obs_repo
        self._policy = policy

    def _daily_spend(self) -> float:
        if self._obs is None:
            return 0.0
        day = datetime.now(timezone.utc).date().isoformat()
        row = self._obs.get_daily(day)
        return float(row.cost_usd) if row else 0.0

    def decide(
        self,
        *,
        importance_score: float,
        operation: str,
        source_count: int = 1,
    ) -> AIBudgetDecision:
        spend = self._daily_spend()
        budget = self._policy.max_daily_ai_cost_usd

        if spend >= budget:
            return AIBudgetDecision(
                allow_llm=False,
                model_tier="none",
                reason="daily_budget_exceeded",
                skip_translation=True,
                skip_embeddings=True,
            )

        if importance_score < self._policy.use_cheap_model_below_importance:
            return AIBudgetDecision(
                allow_llm=operation in ("summarize",),
                model_tier=self.CHEAP_MODEL,
                reason="low_importance_cheap_model",
                skip_translation=importance_score < 0.25,
                skip_embeddings=True,
            )

        if spend >= budget * 0.85:
            return AIBudgetDecision(
                allow_llm=True,
                model_tier=self.CHEAP_MODEL,
                reason="budget_guardrail",
                skip_translation=source_count < 2,
            )

        return AIBudgetDecision(
            allow_llm=True,
            model_tier=self.STANDARD_MODEL,
            reason="normal",
        )

    def estimate_savings_from_skip(self, *, skipped_ops: int, avg_cost: float = 0.002) -> float:
        return skipped_ops * avg_cost
