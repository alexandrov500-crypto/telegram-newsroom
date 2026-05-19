from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from bot.cognitive.runtime import build_cognitive_runtime
from bot.mesh.bus import FederatedCognitiveBus
from bot.mesh.envelope import CognitiveEventEnvelope
from bot.mesh.governance import ConstitutionalGovernance
from bot.mesh.reasoning import CollectiveReasoningEngine
from bot.mesh.repository import MeshRepository
from bot.mesh.runtime import build_federated_cognitive_mesh
from bot.mesh.types import ConsensusVote
from bot.storage.coordination_repository import CoordinationRepository
from bot.storage.db import init_database


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return init_database(tmp_path / "mesh.db")


def test_cognitive_envelope_dedup(db_path: Path) -> None:
    repo = MeshRepository(db_path)
    bus = FederatedCognitiveBus(repo, node_id="n1", region="eu")

    async def _run():
        env = CognitiveEventEnvelope(
            event_type="evaluation.completed",
            payload={"score": 0.8},
            node_id="n1",
            region="eu",
        )
        assert await bus.publish(env)
        assert not await bus.publish(env)

    asyncio.run(_run())


def test_gossip_budget(db_path: Path) -> None:
    repo = MeshRepository(db_path)
    bus = FederatedCognitiveBus(repo, node_id="n1", region="eu", config={"gossip_budget_per_tick": 2})
    remaining = repo.gossip_budget_remaining("n1", "eu")
    assert remaining >= 2


def test_collective_reasoning(db_path: Path) -> None:
    repo = MeshRepository(db_path)
    engine = CollectiveReasoningEngine(repo, node_id="n1", region="eu")
    session = engine.open_session("story:99")
    engine.submit_vote(
        session,
        ConsensusVote(node_id="n1", vote=0.8, confidence=0.9, reason="eu regional"),
    )
    engine.submit_vote(
        session,
        ConsensusVote(node_id="n2", vote=0.6, confidence=0.7, reason="us regional"),
    )
    result = engine.finalize(session)
    assert 0.5 < result.consensus_score < 0.9
    assert result.explanation
    assert len(result.disagreement) >= 0


def test_constitutional_governance(db_path: Path) -> None:
    repo = MeshRepository(db_path)
    gov = ConstitutionalGovernance(repo)
    assert gov.constitution is not None
    d = gov.check_action("constitutional_amend", context={"operator_approved": False})
    assert not d.allowed
    assert d.invariant == "operator_supremacy"
    d2 = gov.allow_learning_apply(operator_approved=True)
    assert d2.allowed


def test_federated_memory_reconcile(db_path: Path) -> None:
    cognitive = build_cognitive_runtime(db_path, node_id="n1", node_region="eu")
    mesh = build_federated_cognitive_mesh(
        db_path, cognitive, node_id="n1", region="eu",
    )
    mid = "story:test123"
    mesh.memory.replicate(memory_id=mid, payload={"title": "A"}, source_region="eu")
    mesh.memory.replicate(memory_id=mid, payload={"title": "B"}, source_region="us")
    rec = mesh.memory.reconcile(mid)
    assert rec["status"] in ("reconciled", "divergent", "single_shard")


def test_mesh_tick(db_path: Path) -> None:
    cognitive = build_cognitive_runtime(db_path, node_id="n1", node_region="eu")
    mesh = build_federated_cognitive_mesh(
        db_path, cognitive, node_id="n1", region="eu",
    )

    async def _run():
        report = await mesh.tick(is_leader=True, mesh_pressure=0.3)
        assert "mesh_health" in report
        assert "agent_offers" in report

    asyncio.run(_run())


def test_mesh_tournament(db_path: Path) -> None:
    cognitive = build_cognitive_runtime(db_path, node_id="n1", node_region="eu")
    mesh = build_federated_cognitive_mesh(
        db_path, cognitive, node_id="n1", region="eu",
    )

    async def _run():
        result = await mesh.simulation.run_tournament(
            ["policy_eval"], lane="mesh_shadow", seed=1,
        )
        assert result.tournament_id
        assert result.scores

    asyncio.run(_run())


def test_mesh_with_federated_sync(db_path: Path) -> None:
    coord = CoordinationRepository(db_path)
    from bot.distributed.federation.learning_sync import FederatedLearningSync

    fl = FederatedLearningSync(coord)
    cognitive = build_cognitive_runtime(db_path, node_id="n1", node_region="eu")
    mesh = build_federated_cognitive_mesh(
        db_path, cognitive, node_id="n1", region="eu", federated_sync=fl,
    )
    mesh.learning.propose_delta("source_weight", {"reuters": 0.05})
    pending = mesh.learning.aggregate_pending()
    assert "aggregated" in pending
