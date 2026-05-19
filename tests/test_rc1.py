from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from bot.rc1.activation.workflow import ActivationStage, PublicActivationOrchestrator
from bot.rc1.baselines.engine import BaselineEngine
from bot.rc1.config.registry import NewsroomConfigRegistry
from bot.rc1.config.validation import ConfigValidationGraph
from bot.rc1.hardening.failure_modes import FailureModeGuard
from bot.rc1.lockdown import Rc1LockdownController
from bot.rc1.repository import Rc1Repository
from bot.rc1.validation.live_traffic import LiveTrafficValidator
from bot.storage.db import init_database


@pytest.fixture
def repo(tmp_path: Path) -> Rc1Repository:
    init_database(tmp_path / "rc1.db")
    return Rc1Repository(tmp_path / "rc1.db")


def test_config_fingerprint_stable() -> None:
    reg = NewsroomConfigRegistry.collect(build_id="test")
    fp1 = reg.fingerprint()
    fp2 = reg.fingerprint()
    assert fp1 == fp2


def test_config_validation_chaos_production_error() -> None:
    import os

    os.environ["APP_ENV"] = "production"
    os.environ["OPS_CHAOS_ENABLED"] = "true"
    reg = NewsroomConfigRegistry.collect(build_id="test")
    report = ConfigValidationGraph().validate(reg)
    assert any(i.code == "chaos_in_production" for i in report.issues)
    os.environ.pop("OPS_CHAOS_ENABLED", None)
    os.environ["APP_ENV"] = "development"


def test_lockdown_blocks_rollout_without_cert() -> None:
    lock = Rc1LockdownController()
    lock.enable()
    ok, reason = lock.allow_rollout_escalation(certified=False)
    assert ok is False
    assert "certification" in reason


def test_activation_advance_requires_cert(repo: Rc1Repository) -> None:
    orch = PublicActivationOrchestrator(repo)
    repo.set_activation(
        stage=ActivationStage.PRECHECK.value,
        previous=None,
        operator_signoff=None,
        snapshot={},
        rollback_point="PRECHECK",
    )
    trans = orch.evaluate_next(certified=False, operator_signoff=True)
    assert trans.next_stage == ActivationStage.CERTIFICATION


def test_baseline_anomaly(repo: Rc1Repository) -> None:
    engine = BaselineEngine(repo)
    for _ in range(30):
        engine.ingest(queue_depth=10)
    report = engine.anomaly_report({"queue_depth": 500.0})
    assert report["unusual"] is True


def test_failure_guard_dlq(repo: Rc1Repository) -> None:
    guard = FailureModeGuard()
    issues = guard.scan(dlq_count=100, queue_depth=10)
    assert any(i["id"] == "dlq_explosion" for i in issues)


def test_live_validation_scores() -> None:
    v = LiveTrafficValidator()
    result = v.evaluate(delivery_success=0.99, trust_avg=0.9, shadow_publish_ratio=0.2)
    assert result["go_live_confidence"] > 0.5
    assert result["publish_integrity"] > 0.5


def test_repository_config_fingerprint(repo: Rc1Repository) -> None:
    repo.save_config_fingerprint(fingerprint="abc", config={"APP_ENV": "staging"}, issues=[])
    stored = repo.get_config_fingerprint()
    assert stored is not None
    assert stored["fingerprint"] == "abc"
