from __future__ import annotations

from pathlib import Path

import pytest

from bot.distributed.cluster.federation import FederatedStoryRegistry
from bot.distributed.cluster.scheduler import DistributedScheduler
from bot.distributed.config import load_cluster_config
from bot.distributed.partitions import route_partition
from bot.distributed.event_bus.factory import create_event_bus
from bot.distributed.federation.learning_sync import FederatedLearningSync
from bot.distributed.partitions import node_owns_partition
from bot.storage.coordination_repository import CoordinationRepository
from bot.storage.db import init_database
from bot.storage.event_store import EventStore


@pytest.fixture
def coord_repo(tmp_path: Path) -> CoordinationRepository:
    db_path = init_database(tmp_path / "cluster.db")
    return CoordinationRepository(db_path)


def test_lease_leader_election(coord_repo: CoordinationRepository) -> None:
    a = coord_repo.try_acquire_lease(
        "cluster_leader",
        node_id="node-a",
        role="operator",
        ttl_sec=30,
    )
    b = coord_repo.try_acquire_lease(
        "cluster_leader",
        node_id="node-b",
        role="operator",
        ttl_sec=30,
    )
    assert a is not None
    assert b is None
    assert coord_repo.current_leader() == "node-a"


def test_global_job_lease(coord_repo: CoordinationRepository) -> None:
    assert coord_repo.try_acquire_job("digest_hourly", node_id="digest-1", ttl_sec=60)
    assert not coord_repo.try_acquire_job("digest_hourly", node_id="digest-2", ttl_sec=60)
    assert coord_repo.try_acquire_job("digest_hourly", node_id="digest-1", ttl_sec=60)


def test_story_federation_optimistic_concurrency(coord_repo: CoordinationRepository) -> None:
    reg = FederatedStoryRegistry(coord_repo, node_id="story-1")
    v1 = reg.commit_update(story_id=42, expected_version=None, payload={"title": "A"})
    assert v1 is not None
    assert v1.version == 1
    conflict = reg.commit_update(story_id=42, expected_version=0, payload={"title": "B"})
    assert conflict is None
    v2 = reg.commit_update(story_id=42, expected_version=1, payload={"title": "B"})
    assert v2 is not None
    assert v2.version == 2


def test_federated_learning_sync(coord_repo: CoordinationRepository) -> None:
    sync = FederatedLearningSync(coord_repo)
    v1 = sync.sync_source_weights({"reuters": 0.9})
    v2 = sync.sync_source_weights({"reuters": 0.95})
    assert v2 > v1
    merged = sync.merge_source_weights({"local": 0.5})
    assert merged["reuters"] > 0.5


def test_partition_routing() -> None:
    topic = route_partition(title="Bitcoin ETF approved by SEC", tags=("crypto",))
    assert topic == "crypto"
    assert node_owns_partition(("global",), "global")


def test_inmemory_distributed_bus(tmp_path: Path) -> None:
    import asyncio

    async def _run() -> None:
        db_path = init_database(tmp_path / "events.db")
        store = EventStore(db_path)
        bus = create_event_bus(backend="inmemory", node_id="test-node", store=store)
        bus.start()
        received: list[str] = []

        async def handler(event) -> None:
            received.append(event.event_type)

        from bot.events.types import signal_detected

        bus.subscribe("SignalDetected", handler)
        await bus.publish(signal_detected(signal_id=1, signal_type="test", confidence=0.9))
        await asyncio.sleep(0.05)
        await bus.stop()
        assert "SignalDetected" in received

    asyncio.run(_run())


def test_coordinator_registers_node(coord_repo: CoordinationRepository, monkeypatch) -> None:
    monkeypatch.setenv("NODE_ID", "coord-test")
    monkeypatch.setenv("NODE_ROLE", "operator")
    cfg = load_cluster_config()
    coord_repo.register_node(
        node_id=cfg.node_id,
        role=cfg.node_role,
        region=cfg.node_region,
    )
    nodes = coord_repo.list_nodes()
    assert any(n.node_id == "coord-test" for n in nodes)


def test_distributed_scheduler(coord_repo: CoordinationRepository) -> None:
    sched = DistributedScheduler(coord_repo, node_id="n1")
    assert sched.try_run_global("digest_morning")
    sched2 = DistributedScheduler(coord_repo, node_id="n2")
    assert not sched2.try_run_global("digest_morning")
