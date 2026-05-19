from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from bot.cognitive.evaluation import EvaluationPipeline
from bot.cognitive.predictive import OperationalSignals, PredictiveOperationsEngine
from bot.cognitive.repository import CognitiveRepository
from bot.cognitive.routing import AdaptiveModelRouter
from bot.cognitive.runtime import build_cognitive_runtime
from bot.cognitive.types import CognitiveContext
from bot.storage.db import init_database


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return init_database(tmp_path / "cognitive.db")


def test_evaluation_pipeline(db_path: Path) -> None:
    repo = CognitiveRepository(db_path)
    pipeline = EvaluationPipeline(repo)

    async def _run():
        results = await pipeline.evaluate(
            "pending_news",
            {
                "target_id": "42",
                "title": "Major policy shift announced in Brussels",
                "summary": "EU leaders agreed on new framework after marathon talks.",
                "priority_score": 0.8,
                "source_count": 3,
                "cluster_size": 2,
                "source_trust": 0.85,
            },
        )
        assert len(results) >= 3
        assert all(0 <= r.score <= 1 for r in results)
        agg = pipeline.aggregate_score("42")
        assert agg is not None

    asyncio.run(_run())


def test_adaptive_router_breaking(db_path: Path) -> None:
    repo = CognitiveRepository(db_path)
    policy = repo.get_active_policy()
    assert policy is not None
    router = AdaptiveModelRouter(repo, policy=policy, node_id="test")
    decision = router.route(
        CognitiveContext(importance_score=0.9, qos_class="breaking", operation="summarize")
    )
    assert decision.model
    assert "breaking" in decision.reason


def test_adaptive_router_budget_guard(db_path: Path) -> None:
    repo = CognitiveRepository(db_path)
    policy = repo.get_active_policy()
    assert policy is not None
    router = AdaptiveModelRouter(repo, policy=policy, node_id="test")
    repo.update_budget_spend(24.0)
    decision = router.route(
        CognitiveContext(importance_score=0.4, qos_class="analytics", operation="summarize")
    )
    assert decision.model


def test_predictive_engine(db_path: Path) -> None:
    repo = CognitiveRepository(db_path)
    engine = PredictiveOperationsEngine(repo)
    signals = OperationalSignals(queue_backlog=600, stream_lag_sec=45, dlq_count=60)
    engine.observe(signals)
    predictions = engine.forecast(signals)
    assert predictions
    actions = engine.preemptive_actions(predictions)
    assert isinstance(actions, list)


def test_memory_recall(db_path: Path) -> None:
    runtime = build_cognitive_runtime(db_path, node_id="n1")
    runtime.memory.remember_story(
        story_id=1,
        title="Ukraine ceasefire talks resume",
        summary="Diplomats met in Geneva.",
        region="eu",
    )
    recalled = runtime.memory.recall("Ukraine ceasefire")
    assert recalled


def test_agent_coordination(db_path: Path) -> None:
    runtime = build_cognitive_runtime(db_path, node_id="n1")

    async def _run():
        session = await runtime.agent_coordinator.coordinate(
            context={"importance_score": 0.9, "evaluation_score": 0.4},
            required_capabilities=["evaluate"],
        )
        assert session.proposals

    asyncio.run(_run())


def test_learning_feedback(db_path: Path) -> None:
    runtime = build_cognitive_runtime(db_path, node_id="n1")
    deltas = runtime.learning.learn_from_feedback(
        target_type="source",
        target_id="reuters",
        rating=0.9,
        source="reuters",
    )
    assert deltas
    rolled = runtime.learning.rollback_last()
    assert rolled >= 0


def test_simulation_shadow_lane(db_path: Path) -> None:
    runtime = build_cognitive_runtime(db_path, node_id="n1")

    async def _run():
        result = await runtime.simulation.run_scenario("policy_eval", lane="shadow", seed=7)
        assert result.run_id
        assert "eval_count" in result.scores or "composite" in result.scores or result.scores

    asyncio.run(_run())


def test_cognitive_runtime_tick(db_path: Path) -> None:
    runtime = build_cognitive_runtime(db_path, node_id="n1")

    async def _run():
        report = await runtime.tick(
            signals=OperationalSignals(queue_backlog=50),
            degradation_mode="normal",
        )
        assert "route_model" in report
        assert "budget" in report

    asyncio.run(_run())


def test_intelligence_graph(db_path: Path) -> None:
    runtime = build_cognitive_runtime(db_path, node_id="n1")
    runtime.graph.link("story:1", "source:reuters", "sourced_from", weight=0.9)
    snap = runtime.graph.snapshot("story:1")
    assert snap.edges

def test_human_feedback(db_path: Path) -> None:
    runtime = build_cognitive_runtime(db_path, node_id="n1")
    deltas = runtime.feedback.promote_source("ap_news", operator_id="admin")
    assert deltas
