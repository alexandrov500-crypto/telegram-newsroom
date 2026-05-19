from __future__ import annotations

import uuid
from dataclasses import dataclass

from bot.config import get_openai_model
from bot.cognitive.repository import CognitiveRepository
from bot.cognitive.types import CognitiveContext, CognitivePolicyDocument, RouteDecision


@dataclass(frozen=True)
class RoutingPolicy:
    default_model: str
    premium_model: str
    local_model: str
    breaking_model: str
    fallback_chain: tuple[str, ...]
    cheap_below_importance: float
    premium_above_importance: float


class AdaptiveModelRouter:
    """Intelligent model routing with cost-aware fallback chains."""

    def __init__(
        self,
        repository: CognitiveRepository,
        *,
        policy: CognitivePolicyDocument,
        node_id: str,
    ) -> None:
        self._repo = repository
        self._node_id = node_id
        r = policy.routing
        self._policy = RoutingPolicy(
            default_model=str(r.get("default_model", get_openai_model())),
            premium_model=str(r.get("premium_model", "gpt-4.1")),
            local_model=str(r.get("local_model", "local")),
            breaking_model=str(r.get("breaking_model", "gpt-4.1")),
            fallback_chain=tuple(r.get("fallback_chain") or [get_openai_model()]),
            cheap_below_importance=float(r.get("cheap_below_importance", 0.35)),
            premium_above_importance=float(r.get("premium_above_importance", 0.85)),
        )

    def route(self, ctx: CognitiveContext) -> RouteDecision:
        budget = self._repo.get_budget_state()
        spend_ratio = 0.0
        if budget["daily_budget_usd"] > 0:
            spend_ratio = budget["daily_spend_usd"] / budget["daily_budget_usd"]

        model = self._policy.default_model
        strategy = "balanced"
        depth = "medium"
        reasoning = "standard"
        lang_path = ctx.extra.get("language", "en")
        reason_parts: list[str] = []

        if ctx.degradation_mode in ("read_only", "operator_only", "replay_only"):
            model = self._policy.local_model
            strategy = "degraded"
            depth = "shallow"
            reason_parts.append(f"degradation={ctx.degradation_mode}")

        elif ctx.qos_class == "breaking":
            model = self._policy.breaking_model
            strategy = "breaking_fast"
            depth = "shallow"
            reasoning = "fast"
            reason_parts.append("breaking_qos")

        elif ctx.importance_score >= self._policy.premium_above_importance:
            model = self._policy.premium_model
            strategy = "premium"
            depth = "deep"
            reasoning = "thorough"
            reason_parts.append("high_importance")

        elif ctx.importance_score < self._policy.cheap_below_importance or spend_ratio > 0.85:
            model = self._policy.fallback_chain[-1] if self._policy.fallback_chain else self._policy.default_model
            strategy = "cost_guard"
            depth = "shallow"
            reason_parts.append("cost_or_low_importance")

        if ctx.latency_pressure > 0.7:
            depth = "shallow"
            strategy = f"{strategy}_latency"
            reason_parts.append("latency_pressure")

        if spend_ratio > 0.95:
            model = self._policy.local_model
            strategy = "budget_exhausted"
            reason_parts.append("budget_cap")

        tokens = 2048 if depth == "deep" else 1024 if depth == "medium" else 512
        est_cost = tokens * 0.000002 if model != self._policy.local_model else 0.0

        decision = RouteDecision(
            route_id=str(uuid.uuid4())[:12],
            model=model,
            strategy=strategy,
            context_tokens=tokens,
            generation_depth=depth,
            reasoning_mode=reasoning,
            language_path=lang_path,
            fallback_chain=self._policy.fallback_chain,
            reason="; ".join(reason_parts) or "default",
            estimated_cost_usd=est_cost,
        )
        self._repo.audit_route(
            decision,
            node_id=self._node_id,
            context={
                "operation": ctx.operation,
                "qos_class": ctx.qos_class,
                "importance": ctx.importance_score,
            },
        )
        try:
            from bot.observability.metrics import record_model_route

            record_model_route(model, strategy)
        except Exception:
            pass
        return decision
