from __future__ import annotations

from dataclasses import dataclass

from bot.adaptive.cost_optimizer import CostOptimizer
from bot.adaptive.feedback import EditorialFeedbackLoop
from bot.adaptive.policies import OperationalMode, PolicyBundle, PolicyEngine
from bot.adaptive.source_weighting import DynamicSourceWeighting
from bot.adaptive.tuning import SelfTuningEngine
from bot.learning.analytics import LearningAnalyticsEngine
from bot.learning.memory_index import LongTermMemoryIndex
from bot.learning.types import DecisionAudit
from bot.replay.engine import ReplayEngine
from bot.runtime.state import runtime_state
from bot.storage.learning_repository import LearningRepository
from bot.storage.observability_repository import ObservabilityRepository
from bot.storage.source_repository import SourceRepository


@dataclass
class ControlPlane:
    """Operator-facing control surface for the adaptive newsroom."""

    policies: PolicyEngine
    feedback: EditorialFeedbackLoop
    tuning: SelfTuningEngine
    source_weights: DynamicSourceWeighting | None
    analytics: LearningAnalyticsEngine
    memory: LongTermMemoryIndex
    cost_optimizer: CostOptimizer
    learning: LearningRepository
    replay: ReplayEngine | None = None

    @classmethod
    def build(
        cls,
        db_path,
        *,
        sources: SourceRepository | None,
        obs: ObservabilityRepository | None = None,
        signal_repo=None,
    ) -> ControlPlane:
        learning = LearningRepository(db_path)
        policies = PolicyEngine(learning)
        policy = policies.active_policy()
        feedback = EditorialFeedbackLoop(learning)
        tuning = SelfTuningEngine(learning, policies, feedback)
        tuning.sync_from_policy()
        source_weights = (
            DynamicSourceWeighting(learning, sources)
            if sources is not None
            else None
        )
        analytics = LearningAnalyticsEngine(learning, signal_repo)
        memory = LongTermMemoryIndex(learning)
        cost_optimizer = CostOptimizer(obs, policy=policy)
        replay = ReplayEngine(db_path, learning=learning, policies=policies)
        return cls(
            policies=policies,
            feedback=feedback,
            tuning=tuning,
            source_weights=source_weights,  # type: ignore[arg-type]
            analytics=analytics,
            memory=memory,
            cost_optimizer=cost_optimizer,
            learning=learning,
            replay=replay,
        )

    def set_mode(self, mode: str) -> PolicyBundle:
        runtime_state.operational_mode = mode
        policy = self.policies.set_mode(mode)
        self.cost_optimizer._policy = policy  # noqa: SLF001
        return policy

    def maintenance_mode(self, enabled: bool) -> None:
        runtime_state.ingestion_paused = enabled
        runtime_state.maintenance_mode = enabled

    def record_decision(self, audit: DecisionAudit) -> int:
        from bot.observability.metrics import record_agent_decision

        record_agent_decision(audit.action)
        return self.learning.record_audit(audit)

    def run_learning_cycle(self) -> dict:
        signals = self.feedback.derive_feedback_signals()
        adjustments = self.tuning.apply_feedback(signals)
        scores = self.analytics.compute_scores()
        sources_updated = 0
        if self.source_weights is not None:
            sources_updated = self.source_weights.recompute_all()
        return {
            "feedback_signals": len(signals),
            "tuning_adjustments": adjustments,
            "scores": scores,
            "sources_updated": sources_updated,
        }

    def daily_cost_summary(self) -> dict:
        spend = self.cost_optimizer._daily_spend()  # noqa: SLF001
        budget = self.policies.active_policy().max_daily_ai_cost_usd
        return {
            "spend_usd": round(spend, 4),
            "budget_usd": budget,
            "remaining_usd": round(max(0.0, budget - spend), 4),
        }

    def list_modes(self) -> list[str]:
        return [m.value for m in OperationalMode]
