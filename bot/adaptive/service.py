from __future__ import annotations

import logging

from bot.adaptive.policies import PolicyBundle
from bot.control_plane.service import ControlPlane
from bot.learning.types import DecisionAudit
from bot.signals.types import PriorityDecision

logger = logging.getLogger(__name__)


class AdaptiveOperationsService:
    """Bridge ingest/signal decisions with learning and control plane."""

    def __init__(self, control_plane: ControlPlane) -> None:
        self._cp = control_plane

    @property
    def control_plane(self) -> ControlPlane:
        return self._cp

    def active_policy(self) -> PolicyBundle:
        return self._cp.policies.active_policy()

    def apply_policy_to_priority(
        self,
        decision: PriorityDecision,
        *,
        source_count: int,
        importance: float,
    ) -> PriorityDecision:
        policy = self.active_policy()
        if policy.require_multi_source_confirmation and source_count < 2:
            if decision.action == "publish_immediately":
                return PriorityDecision(
                    editorial_priority_score=decision.editorial_priority_score,
                    action="wait_confirmation",
                    reason=decision.reason + "+policy_multi_source",
                )
        if decision.editorial_priority_score < policy.suppress_below:
            return PriorityDecision(
                editorial_priority_score=decision.editorial_priority_score,
                action="suppress",
                reason="policy_suppress_floor",
            )
        if (
            decision.editorial_priority_score >= policy.auto_publish_threshold
            and importance >= policy.escalation_threshold
        ):
            return PriorityDecision(
                editorial_priority_score=decision.editorial_priority_score,
                action="publish_immediately",
                reason=decision.reason + "+policy_auto",
            )
        return decision

    def audit_priority_decision(
        self,
        decision: PriorityDecision,
        *,
        pending_news_id: int | None,
        story_id: int | None,
        signal_id: int | None,
        scores: dict[str, float],
    ) -> None:
        audit = DecisionAudit(
            action=decision.action,
            reason=[decision.reason],
            scores=scores,
            policy=self.active_policy().name,
            pending_news_id=pending_news_id,
            story_id=story_id,
            signal_id=signal_id,
        )
        self._cp.record_decision(audit)

    def index_narrative_memory(
        self,
        *,
        title: str,
        summary: str | None,
        entities: list[str],
    ) -> None:
        self._cp.memory.index_story(title=title, summary=summary, entities=entities)
        self._cp.memory.index_geopolitical_pattern(title, summary)

    def memory_context(self, title: str) -> str:
        return self._cp.memory.context_block(title)

    def effective_source_trust(self, source_name: str, base_trust: float) -> float:
        if self._cp.source_weights is None:
            return base_trust
        try:
            return self._cp.source_weights.effective_trust(source_name)
        except Exception:
            return base_trust

    def ai_budget_for(self, *, importance: float, operation: str, source_count: int = 1):
        self._cp.cost_optimizer._policy = self.active_policy()  # noqa: SLF001
        return self._cp.cost_optimizer.decide(
            importance_score=importance,
            operation=operation,
            source_count=source_count,
        )
