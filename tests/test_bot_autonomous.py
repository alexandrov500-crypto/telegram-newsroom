from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from bot.policy.evaluator import PolicyContext
from bot.policy.repository import PolicyRepository
from bot.policy.runtime import PolicyRuntime
from bot.policy.types import WorkflowQoSClass
from bot.runtime.adaptive_scheduler import AdaptiveScheduler, LoadSignals
from bot.runtime.degradation import DegradationStateMachine
from bot.runtime.autonomous_runtime import build_autonomous_runtime
from bot.storage.coordination_repository import CoordinationRepository
from bot.storage.db import init_database
from bot.chaos.runner import run_chaos_suite


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return init_database(tmp_path / "autonomous.db")


def test_policy_evaluator_publish_limit(db_path: Path) -> None:
    repo = PolicyRepository(db_path)
    runtime = PolicyRuntime(repo, node_id="test")
    ctx = PolicyContext(
        publishes_last_minute=100,
        workflow_class=WorkflowQoSClass.PUBLISH.value,
    )
    decision = runtime.decide("publish", ctx, audit=False)
    assert not decision.allowed


def test_degradation_state_machine(db_path: Path) -> None:
    sm = DegradationStateMachine(db_path)
    assert sm.current().mode == "normal"
    sm.transition("publish_safe", reason="test", force=True)
    assert sm.current().mode == "publish_safe"
    sm.rollback()
    assert sm.current().mode == "normal"


def test_adaptive_scheduler_shedding(db_path: Path) -> None:
    coord = CoordinationRepository(db_path)
    repo = PolicyRepository(db_path)
    policy = PolicyRuntime(repo, node_id="n1")
    sched = AdaptiveScheduler(coord, node_id="n1", policy=policy)
    sched.update_signals(LoadSignals(queue_backlog=800))
    d = sched.try_schedule("analytics_job", qos_class=WorkflowQoSClass.ANALYTICS.value)
    assert not d.acquired


def test_autonomous_runtime_tick(db_path: Path) -> None:
    coord = CoordinationRepository(db_path)
    coord.register_node(node_id="n1", role="operator", region="eu")
    runtime = build_autonomous_runtime(
        db_path,
        node_id="n1",
        node_region="eu",
        coordination=coord,
    )

    async def _run():
        result = await runtime.tick(
            node_id="n1",
            node_region="eu",
            is_leader=True,
            queue_backlog=10,
            apply_operations=False,
        )
        assert "health" in result
        assert "degradation" in result

    asyncio.run(_run())


def test_chaos_suite(db_path: Path) -> None:
    coord = CoordinationRepository(db_path)
    runtime = build_autonomous_runtime(
        db_path,
        node_id="c1",
        node_region="global",
        coordination=coord,
    )

    async def _run():
        results = await run_chaos_suite(
            recovery=runtime.recovery,
            idempotency=runtime.replay_guard._idempotency or __import__(
                "bot.publishing.idempotency",
                fromlist=["PublishIdempotencyStore"],
            ).PublishIdempotencyStore(db_path),
            scheduler=runtime.scheduler,
            degradation=runtime.degradation,
            coordination=coord,
        )
        assert all(r.passed for r in results), [r for r in results if not r.passed]

    from bot.publishing.idempotency import PublishIdempotencyStore

    runtime.replay_guard._idempotency = PublishIdempotencyStore(db_path)
    asyncio.run(_run())
