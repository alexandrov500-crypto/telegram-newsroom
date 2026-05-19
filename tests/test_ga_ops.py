from __future__ import annotations

from pathlib import Path

import pytest

from bot.ga_ops.quality.validator import AiQualityValidator
from bot.ga_ops.readiness.evaluator import GaReadinessEvaluator, GaReadinessState
from bot.ga_ops.repository import GaOpsRepository
from bot.ga_ops.rollback.safety import RollbackSafetyManager
from bot.ga_ops.scaling.readiness import ScalingReadinessEvaluator
from bot.ga_ops.traffic.guardrails import PublicTrafficGuardrails, TrafficPressure
from bot.storage.db import init_database


@pytest.fixture
def repo(tmp_path: Path) -> GaOpsRepository:
    init_database(tmp_path / "ga.db")
    return GaOpsRepository(tmp_path / "ga.db")


def test_traffic_blocks_duplicate_narrative(repo: GaOpsRepository) -> None:
    g = PublicTrafficGuardrails(repo, max_publishes_per_hour=100)
    g.record_publish(narrative_key="same-story")
    v = g.evaluate(narrative_key="same-story", trust_score=0.9)
    assert v.allowed is False
    assert v.reason == "duplicate_narrative"


def test_traffic_critical_on_surge(repo: GaOpsRepository) -> None:
    g = PublicTrafficGuardrails(repo, max_publishes_per_hour=5, surge_queue_threshold=100)
    v = g.evaluate(queue_depth=500, trust_score=0.9)
    assert v.pressure == TrafficPressure.TRAFFIC_PRESSURE_CRITICAL


def test_quality_blocks_thin_summary(repo: GaOpsRepository) -> None:
    q = AiQualityValidator(repo)
    v = q.evaluate(headline="Valid headline here", summary="short")
    assert v.passed is False
    assert "summary_thin" in v.blockers


def test_ga_ready_when_all_pass() -> None:
    ev = GaReadinessEvaluator(min_score=0.88)
    r = ev.evaluate(
        uptime_stable=True,
        slo_violations=0,
        critical_incidents=0,
        confidence_trend=0.9,
        quality_avg=0.8,
        publish_integrity=0.95,
        certification_state="CERTIFIED",
    )
    assert r.state == GaReadinessState.GA_READY


def test_rollback_dry_run_no_republish(repo: GaOpsRepository) -> None:
    rb = RollbackSafetyManager(repo)
    rb.create_snapshot(stage="test", detail={"rollout": "shadow"})
    dry = rb.dry_run(target_stage="INTERNAL_SHADOW")
    assert dry["would_republish"] is False
    assert dry["audit_preserved"] is True


def test_scaling_recommends_workers() -> None:
    s = ScalingReadinessEvaluator()
    r = s.evaluate(queue_depth=700, worker_total=4, worker_stale=1)
    assert r["scaling_risk_score"] > 0.5
    assert "scale_ingest_worker" in r["recommended_actions"]
