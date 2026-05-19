from __future__ import annotations

from pathlib import Path

import pytest

from bot.ingestion.feed_resilience import FeedResilienceLayer
from bot.operations.operational_readiness import compute_operational_readiness
from bot.operations.repository import OperationsRepository
from bot.operations.runtime_supervisor import RuntimeSupervisor
from bot.observability.loop_registry import LoopHeartbeatRegistry
from bot.operations.replay_hardening import ReplaySustainability
from bot.publishing.telegram_reliability import TelegramDeliveryReliability


@pytest.fixture
def ops_repo(tmp_path: Path) -> OperationsRepository:
    from bot.storage.db import init_database

    db = init_database(tmp_path / "continuous_ops.db")
    return OperationsRepository(db)


def test_loop_registry_stalled() -> None:
    import time

    reg = LoopHeartbeatRegistry()
    reg.register("test-loop", 1.0)
    reg.heartbeat("test-loop", 0.1)
    lb = reg._loops["test-loop"]
    lb.last_tick_monotonic = time.monotonic() - 200
    assert reg.stalled_loops()[0].name == "test-loop"


def test_telegram_dedup(ops_repo: OperationsRepository) -> None:
    rel = TelegramDeliveryReliability(ops_repo)
    assert rel.should_send("key_a")
    assert not rel.should_send("key_a")


def test_feed_quarantine(ops_repo: OperationsRepository) -> None:
    layer = FeedResilienceLayer(ops_repo)
    ops_repo.quarantine_feed("http://bad.example/feed", source_name="bad", reason="test")
    verdict = layer.evaluate_feed("http://bad.example/feed", source_name="bad")
    assert not verdict.allowed
    assert verdict.quarantined


def test_operational_readiness_deterministic() -> None:
    a = compute_operational_readiness(
        signals={"mesh_health": 0.9, "epistemic_stability": 0.85},
        ops_report={"operator_fatigue": 0.2, "replay_divergence": 0.05},
    )
    b = compute_operational_readiness(
        signals={"mesh_health": 0.9, "epistemic_stability": 0.85},
        ops_report={"operator_fatigue": 0.2, "replay_divergence": 0.05},
    )
    assert a.overall == b.overall


def test_replay_sustainability(ops_repo: OperationsRepository) -> None:
    replay = ReplaySustainability(ops_repo._db_path, ops_repo)
    report = replay.assess_sustainability()
    assert 0.0 <= report["score"] <= 1.0


def test_ops_incident_lifecycle(ops_repo: OperationsRepository) -> None:
    from bot.operations.archaeology import FailureArchaeology
    from bot.operations.incident_lifecycle import IncidentLifecycleManager

    mgr = IncidentLifecycleManager(ops_repo, FailureArchaeology(ops_repo))
    inc = mgr.open_incident(
        title="Test stall",
        severity="warning",
        detail="rss loop stalled",
        correlation_key="test:stall",
        replay_refs=["evt_1"],
    )
    assert mgr.acknowledge(inc.incident_id, operator_id="op1")
    assert mgr.resolve(inc.incident_id, operator_id="op1", note="recovered")
    assert mgr.export_bundle(inc.incident_id) is not None


def test_evidence_bundle_persist(ops_repo: OperationsRepository, tmp_path: Path) -> None:
    from bot.operations.evidence_bundles import ContinuousEvidenceGenerator

    gen = ContinuousEvidenceGenerator(ops_repo)
    bundle = gen.build_bundle(
        signals={"mesh_health": 0.9, "queue_backlog": 2},
        ops_report={"long_run_health": 0.85, "operator_fatigue": 0.1},
    )
    json_path, md_path = gen.persist(
        bundle,
        json_dir=tmp_path / "artifacts",
        markdown_path=tmp_path / "BURN_IN_REPORT.md",
    )
    assert json_path is not None and json_path.exists()
    assert md_path is not None and md_path.exists()


def test_operator_workflow_report(ops_repo: OperationsRepository) -> None:
    from bot.operations.operator_workflow_reports import OperatorWorkflowReportGenerator

    ops_repo.start_operator_session("s1", "triage", "op1")
    ops_repo.record_operator_action("s1")
    ops_repo.end_operator_session("s1")
    report = OperatorWorkflowReportGenerator(ops_repo).build(hours=24)
    assert report.sessions >= 1


def test_runtime_supervisor_probe() -> None:
    import asyncio

    async def _run() -> None:
        sup = RuntimeSupervisor(queue_backlog_fn=lambda: 0)
        report = await sup.probe()
        assert report.queue_backlog == 0

    asyncio.run(_run())
