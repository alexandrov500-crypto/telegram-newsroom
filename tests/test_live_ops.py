from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from bot.events.envelope import EventEnvelope
from bot.live_ops.contracts import LiveEventType, build_envelope
from bot.live_ops.event_bus import NewsroomLiveEventBus
from bot.live_ops.recovery.disaster_recovery import DisasterRecoveryManager
from bot.live_ops.cognition.evolution import CognitionEvolutionOrchestrator
from bot.live_ops.storage.abstraction import SqliteNewsroomBackend, resolve_storage_stack
from bot.live_ops.workers.topology import WorkerMeshRegistry, WorkerRole
from bot.storage.db import init_database


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    init_database(tmp_path / "live_ops.db")
    return tmp_path / "live_ops.db"


def test_live_event_contract_validation() -> None:
    env = build_envelope(
        LiveEventType.STORY_INGESTED,
        {"story_id": 1, "source": "rss"},
    )
    assert env.event_type == "StoryIngested"
    with pytest.raises(ValueError):
        build_envelope(LiveEventType.STORY_INGESTED, {"story_id": 1})


def test_event_bus_emit_and_handler() -> None:
    bus = NewsroomLiveEventBus()
    seen: list[EventEnvelope] = []

    async def handler(env: EventEnvelope) -> None:
        seen.append(env)

    async def run() -> None:
        bus.subscribe(LiveEventType.COGNITION_COMPLETED, handler)
        await bus.emit(
            LiveEventType.COGNITION_COMPLETED,
            {"story_id": 2, "confidence": 0.8, "duration_ms": 1200},
        )

    asyncio.run(run())
    assert len(seen) == 1
    assert seen[0].payload["story_id"] == 2


def test_storage_stack_sqlite_default(db_path: Path) -> None:
    stack = resolve_storage_stack(db_path)
    assert stack["primary_ok"] is True
    assert stack["primary"].backend_name() == "sqlite"
    assert stack["dual_write"] is False


def test_worker_mesh_registry() -> None:
    reg = WorkerMeshRegistry()
    reg.register(WorkerRole.INGEST, "node-a", queues=("ingest",))
    reg.heartbeat(WorkerRole.INGEST, "node-a")
    snap = reg.snapshot()
    assert len(snap) == 1
    assert snap[0]["role"] == "ingest-worker"


def test_cognition_evolution_vote() -> None:
    orch = CognitionEvolutionOrchestrator()
    result = orch.vote_editorial(
        story_id=10,
        source_trust=0.9,
        contradiction_score=0.1,
        confidence=0.85,
    )
    assert result.decision in ("approve_candidate", "review", "block")
    assert result.consensus_score > 0.5


def test_disaster_recovery_export(db_path: Path) -> None:
    mgr = DisasterRecoveryManager(db_path=db_path, export_dir=db_path.parent / "exports")
    path = mgr.export_snapshot(label="test")
    assert path.exists()
    assert path.stat().st_size > 10


def test_sqlite_backend_ping(db_path: Path) -> None:
    backend = SqliteNewsroomBackend(db_path)
    assert backend.ping() is True


def test_go_live_readiness_blockers() -> None:
    from bot.live_ops.coordinator import LiveOpsCoordinator
    from bot.live_ops.event_bus import NewsroomLiveEventBus
    from bot.live_ops.recovery.disaster_recovery import DisasterRecoveryManager
    from bot.live_ops.settings import LiveOpsSettings
    from bot.live_ops.stability.long_run import LongRunStabilityTracker
    from bot.live_ops.tenancy.scope import TenantRegistry
    from bot.live_ops.workers.topology import WorkerMeshRegistry

    coord = LiveOpsCoordinator(
        settings=LiveOpsSettings(enabled=True),
        event_bus=NewsroomLiveEventBus(),
        recovery=DisasterRecoveryManager(db_path=Path("/tmp/x.db")),
        workers=WorkerMeshRegistry(),
        stability=LongRunStabilityTracker(),
        tenants=TenantRegistry(),
        cognition=CognitionEvolutionOrchestrator(),
    )
    readiness = coord.go_live_readiness(
        reliability_score=0.4,
        safety_ok=False,
        queue_depth=600,
    )
    assert readiness["ready"] is False
    assert "reliability_low" in readiness["blockers"]
