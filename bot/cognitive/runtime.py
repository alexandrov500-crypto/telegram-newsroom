from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bot.cognitive.agents import AgentRegistry, MultiAgentCoordinator
from bot.cognitive.cost import CostIntelligence
from bot.cognitive.evaluation import EvaluationPipeline, EvaluationPolicy
from bot.cognitive.feedback import HumanInTheLoopService
from bot.cognitive.graph import EditorialIntelligenceGraph
from bot.cognitive.integrations import set_active_router
from bot.cognitive.learning import LearningCoordinator
from bot.cognitive.memory import EditorialMemorySystem
from bot.cognitive.predictive import OperationalSignals, PredictiveOperationsEngine
from bot.cognitive.repository import CognitiveRepository
from bot.cognitive.routing import AdaptiveModelRouter
from bot.cognitive.simulation import SimulationEnvironment
from bot.cognitive.types import CognitiveContext, CognitivePolicyDocument

logger = logging.getLogger(__name__)


@dataclass
class CognitiveEditorialRuntime:
    """Self-optimizing editorial intelligence facade."""

    repository: CognitiveRepository
    policy: CognitivePolicyDocument
    evaluation: EvaluationPipeline
    router: AdaptiveModelRouter
    memory: EditorialMemorySystem
    graph: EditorialIntelligenceGraph
    agents: AgentRegistry
    agent_coordinator: MultiAgentCoordinator
    learning: LearningCoordinator
    cost: CostIntelligence
    predictive: PredictiveOperationsEngine
    simulation: SimulationEnvironment
    feedback: HumanInTheLoopService
    node_id: str

    async def tick(
        self,
        *,
        signals: OperationalSignals | None = None,
        degradation_mode: str = "normal",
        apply_learning: bool = True,
    ) -> dict[str, Any]:
        sig = signals or OperationalSignals()
        self.predictive.observe(sig)
        predictions = self.predictive.forecast(sig)
        preemptive = self.predictive.preemptive_actions(predictions)

        pruned = self.memory.maintenance()
        report: dict[str, Any] = {
            "predictions": len(predictions),
            "preemptive": preemptive,
            "memory_pruned": pruned,
            "budget": self.repository.get_budget_state(),
        }

        if apply_learning and predictions:
            for p in predictions:
                if p.forecast_type == "backlog_growth" and p.predicted_value > 0.8:
                    self.repository.cognitive_audit(
                        "preemptive_throttle",
                        p.explanation,
                        node_id=self.node_id,
                        context={"confidence": p.confidence},
                    )

        ctx = CognitiveContext(
            degradation_mode=degradation_mode,
            latency_pressure=min(1.0, sig.stream_lag_sec / 60.0),
            qos_class="standard",
        )
        route = self.router.route(ctx)
        cost_dec = self.cost.decide(ctx)
        report["route_model"] = route.model
        report["cost_reason"] = cost_dec.reason

        session = await self.agent_coordinator.coordinate(
            context={
                "importance_score": 0.5,
                "queue_backlog": sig.queue_backlog,
            },
        )
        report["agent_proposals"] = len(session.proposals)

        try:
            from bot.observability.metrics import set_cognitive_health

            health = 1.0 - min(1.0, sig.queue_backlog / 1000.0)
            set_cognitive_health(health)
        except Exception:
            pass
        return report

    async def evaluate_pending(
        self,
        *,
        target_type: str,
        payload: dict,
    ) -> list[dict[str, Any]]:
        results = await self.evaluation.evaluate(target_type, payload)
        target_id = str(payload.get("target_id") or payload.get("id", "unknown"))
        story_id = payload.get("story_id")
        if story_id is not None:
            for r in results:
                self.graph.link_story_evaluation(int(story_id), r.evaluation_id, r.score)
        agg = self.evaluation.aggregate_score(target_id)
        return [{"evaluator": r.evaluator_name, "score": r.score} for r in results] + (
            [{"aggregate": agg}] if agg is not None else []
        )


def build_cognitive_runtime(
    db_path: Path,
    *,
    node_id: str,
    node_region: str = "global",
) -> CognitiveEditorialRuntime:
    repo = CognitiveRepository(db_path)
    policy = repo.get_active_policy()
    if policy is None:
        from bot.cognitive.schema import DEFAULT_COGNITIVE_POLICY

        policy = DEFAULT_COGNITIVE_POLICY
        repo.save_policy(policy, activate=True)

    evaluation = EvaluationPipeline(repo, EvaluationPolicy(enabled=policy.evaluation_enabled))
    router = AdaptiveModelRouter(repo, policy=policy, node_id=node_id)
    set_active_router(router)
    memory = EditorialMemorySystem(repo, policy)
    graph = EditorialIntelligenceGraph(repo)
    registry = AgentRegistry(repo)
    coordinator = MultiAgentCoordinator(registry)
    learning = LearningCoordinator(repo, policy)
    cost = CostIntelligence(repo, policy)
    predictive = PredictiveOperationsEngine(repo)
    simulation = SimulationEnvironment(repo, policy, evaluation=evaluation, router=router)
    feedback = HumanInTheLoopService(repo, learning)

    runtime = CognitiveEditorialRuntime(
        repository=repo,
        policy=policy,
        evaluation=evaluation,
        router=router,
        memory=memory,
        graph=graph,
        agents=registry,
        agent_coordinator=coordinator,
        learning=learning,
        cost=cost,
        predictive=predictive,
        simulation=simulation,
        feedback=feedback,
        node_id=node_id,
    )
    logger.info(
        "event=cognitive_runtime_built node_id=%s region=%s policy_v=%s",
        node_id,
        node_region,
        policy.version,
    )
    return runtime
