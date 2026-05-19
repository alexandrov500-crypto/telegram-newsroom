from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from bot.ops_playbook.auditor.compliance import OperationsAuditor
from bot.ops_playbook.campaign.mode import CampaignModeEngine
from bot.ops_playbook.factory import build_ops_playbook_stack
from bot.ops_playbook.repository import OpsPlaybookRepository
from bot.ops_playbook.shift.handoff import ShiftHandoffEngine
from bot.ops_playbook.training.simulator import OperatorTrainingSimulator
from bot.storage.db import init_database


@pytest.fixture
def repo(tmp_path: Path) -> OpsPlaybookRepository:
    init_database(tmp_path / "pb.db")
    return OpsPlaybookRepository(tmp_path / "pb.db")


def test_shift_handoff_and_ack(repo: OpsPlaybookRepository) -> None:
    engine = ShiftHandoffEngine(repo)
    sig = {"rollout_stage": "INTERNAL_SHADOW", "operator_attention": 0.9, "queue_depth": 10}
    text = engine.take_shift("op1", sig)
    assert "Shift handoff" in text
    ack = engine.acknowledge("op2")
    assert "acknowledged" in ack
    history = repo.shift_ack_history()
    assert len(history) >= 2


def test_campaign_mode(repo: OpsPlaybookRepository) -> None:
    camp = CampaignModeEngine(repo)
    assert "ON" in camp.start("election")
    assert "election" in camp.status()
    assert "OFF" in camp.stop()


def test_training_never_mutates_rollout(repo: OpsPlaybookRepository) -> None:
    sim = OperatorTrainingSimulator(repo)
    sim.enable_training_mode()
    _, text = sim.run_drill("rollback_rehearsal", "op1")
    assert "simulated" in text.lower()
    drills = repo.recent_drills()
    assert drills[0]["simulated"] == 1


def test_auditor_compliance(repo: OpsPlaybookRepository) -> None:
    auditor = OperationsAuditor(repo)
    score, findings = auditor.run_audit(
        {"rollout_stage": "INTERNAL_SHADOW", "quality_avg": 0.5, "rollback_ready": False},
    )
    assert score < 1.0
    assert len(findings) >= 1


def test_coordinator_tick(tmp_path: Path) -> None:
    async def _run() -> None:
        coord = build_ops_playbook_stack(tmp_path / "pb2.db")
        init_database(tmp_path / "pb2.db")
        await coord.startup()
        tick = await coord.tick(
            signals={"trust_score": 0.9, "quality_avg": 0.85, "queue_depth": 5},
        )
        assert "launch_risk" in tick

    asyncio.run(_run())
