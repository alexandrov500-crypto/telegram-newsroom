from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from bot.ops_certification.certification.engine import (
    CertificationState,
    ProductionCertificationEngine,
)
from bot.ops_certification.chaos.scenarios import ChaosDrillRunner, ChaosScenario
from bot.ops_certification.governance.controller import GovernanceController
from bot.ops_certification.repository import OpsCertificationRepository
from bot.ops_certification.security.audit_chain import ImmutableAuditChain
from bot.ops_certification.slo.engine import SloEngine, SloName
from bot.storage.db import init_database


@pytest.fixture
def repo(tmp_path: Path) -> OpsCertificationRepository:
    init_database(tmp_path / "ops_cert.db")
    return OpsCertificationRepository(tmp_path / "ops_cert.db")


def test_certification_not_ready_when_fatal(repo: OpsCertificationRepository) -> None:
    engine = ProductionCertificationEngine(min_score=0.85)
    result = engine.evaluate(fatal_incidents=1, worker_total=6, worker_stale=0)
    assert result.state == CertificationState.NOT_READY
    assert "no_fatal_incidents" in result.blockers


def test_certification_certified_when_all_pass() -> None:
    engine = ProductionCertificationEngine(min_score=0.85)
    result = engine.evaluate(
        fatal_incidents=0,
        worker_total=6,
        worker_stale=0,
        queue_depth=10,
        replay_ok=True,
        recovery_ok=True,
        telegram_health=0.99,
        event_bus_dlq=0,
        stability_score=0.9,
        slo_violations=0,
    )
    assert result.state == CertificationState.CERTIFIED


def test_slo_violation_detection() -> None:
    slo = SloEngine(window_hours=1.0)
    for _ in range(20):
        slo.record(SloName.PUBLISH_LATENCY, value=60.0, success=False)
    ev = slo.evaluate(SloName.PUBLISH_LATENCY)
    assert ev.violated is True
    assert ev.burn_rate > 0


def test_chaos_drill_passes() -> None:
    runner = ChaosDrillRunner(min_survivability=0.5)

    async def run() -> None:
        result = await runner.run(ChaosScenario.OPENAI_LATENCY, safety_check=lambda: 0.9)
        assert result.status == "passed"
        assert result.survivability_score >= 0.5

    asyncio.run(run())


def test_audit_chain_integrity(repo: OpsCertificationRepository) -> None:
    chain = ImmutableAuditChain(repo)
    signed = chain.sign_action("42", "/publish_pause", payload={"ok": True})
    ok, reason = chain.verify_chain(signed.action_id)
    assert ok is True
    assert reason == "ok"


def test_governance_freeze(repo: OpsCertificationRepository) -> None:
    gov = GovernanceController(repo)
    gov.freeze_editorial(reason="test")
    snap = gov.snapshot()
    assert snap["editorial_frozen"] is True
    gov.unfreeze_editorial()
    assert gov.snapshot()["editorial_frozen"] is False


def test_repository_chaos_and_slo(repo: OpsCertificationRepository) -> None:
    repo.record_chaos_run(
        run_id="r1",
        scenario="openai_latency",
        status="passed",
        survivability_score=0.88,
    )
    runs = repo.latest_chaos_runs()
    assert runs[0]["scenario"] == "openai_latency"
    repo.record_slo_snapshot(
        slo_name="uptime",
        window_hours=1.0,
        compliance_ratio=0.999,
        burn_rate=0.1,
        error_budget_remaining=0.9,
        violated=False,
    )
    hist = repo.slo_history("uptime", limit=1)
    assert hist[0]["compliance_ratio"] == 0.999
