from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from bot.operations.burnin_reports import BurnInReportGenerator
from bot.operations.epistemic_monitor import EpistemicStabilityMonitor
from bot.operations.runtime import build_operations_platform
from bot.operations.staging_runtime import StagingRuntimeValidator
from bot.storage.db import init_database


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return init_database(tmp_path / "hardening.db")


def test_burnin_report_generator(db_path: Path) -> None:
    ops = build_operations_platform(db_path, node_id="t", region="eu")
    run_id = ops.burnin.start("24h")
    ops.burnin.record_sample({"health_score": 0.9, "epistemic_stability": 0.85, "queue_backlog": 5})
    ops.burnin.record_sample({"health_score": 0.88, "epistemic_stability": 0.84, "queue_backlog": 8})
    gen = BurnInReportGenerator(ops.repository, ops.burnin)
    summary = gen.generate_period_report(run_id, period="rolling")
    assert summary.run_id == run_id
    assert "Health mean" in summary.markdown


def test_epistemic_longitudinal(db_path: Path) -> None:
    mon = EpistemicStabilityMonitor(build_operations_platform(db_path, node_id="t", region="eu").repository)
    report = mon.record_snapshot(
        confidence_mean=0.8,
        uncertainty_mean=0.2,
        open_contradictions=3,
        misinfo_pressure=0.1,
        diversity_score=0.6,
    )
    assert report.diversity_score == 0.6
    series = mon.timeline_for_explorer()
    assert len(series) >= 1


def test_replay_indexes(db_path: Path) -> None:
    ops = build_operations_platform(db_path, node_id="t", region="eu")
    applied = ops.replay.ensure_replay_indexes()
    assert isinstance(applied, list)
    health = ops.replay.measure_replay_health()
    assert health.divergence_rate >= 0.0


def test_operational_tick_hardening(db_path: Path) -> None:
    ops = build_operations_platform(db_path, node_id="t", region="eu")
    ops.burnin.start("7d")

    async def _run():
        return await ops.operational_tick(
            signals={
                "health_score": 0.9,
                "queue_backlog": 10,
                "epistemic_stability": 0.85,
                "token_spend_usd": 1.0,
            },
            run_epistemic_snapshot=True,
            run_replay_indexes=True,
            run_burnin_report=True,
        )

    report = asyncio.run(_run())
    assert "operator_alerts_open" in report
    assert "replay_indexes" in report


def test_incident_export(db_path: Path, tmp_path: Path) -> None:
    ops = build_operations_platform(db_path, node_id="t", region="eu")
    export = ops.incident_ops.export_bundle(
        "test-inc",
        timeline=[{"at": "now", "event": "test"}],
        export_dir=tmp_path / "incidents",
    )
    assert export.path.exists()
    assert export.bundle_id


def test_simplification_dedupe(db_path: Path) -> None:
    ops = build_operations_platform(db_path, node_id="t", region="eu")
    first = ops.simplification.dedupe_enqueue(
        alert_key="test:dedupe",
        category="info",
        title="Once",
    )
    second = ops.simplification.dedupe_enqueue(
        alert_key="test:dedupe",
        category="info",
        title="Twice",
    )
    assert first is not None
    assert second is None


def test_staging_smoke_checks() -> None:
    report = StagingRuntimeValidator().smoke_report()
    assert "Startup validation" in report


def test_readiness_nightly(db_path: Path) -> None:
    ops = build_operations_platform(db_path, node_id="t", region="eu")

    async def _run():
        return await ops.readiness.nightly_run(
            {"health_score": 0.9, "epistemic_stability": 0.9, "queue_backlog": 0},
            chaos_components=None,
        )

    verdict = asyncio.run(_run())
    assert verdict.staging_score > 0
