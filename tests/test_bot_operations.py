from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from bot.operations.burnin import BurnInRunner
from bot.operations.certification import ProductionReadinessCertification
from bot.operations.ergonomics import OperationalErgonomics
from bot.operations.feed_validation import FeedValidationLayer
from bot.operations.repository import OperationsRepository
from bot.operations.runtime import build_operations_platform
from bot.operations.storage import StorageSustainability
from bot.storage.db import init_database


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return init_database(tmp_path / "ops.db")


def test_burnin_runner(db_path: Path) -> None:
    repo = OperationsRepository(db_path)
    runner = BurnInRunner(repo)
    run_id = runner.start("24h")
    runner.record_sample({"health_score": 0.9, "queue_backlog": 10})
    runner.record_sample({"health_score": 0.85, "queue_backlog": 20})
    baseline = runner.complete(health_score=0.87, summary={"ok": True})
    assert baseline is not None
    assert baseline.samples >= 2


def test_feed_validation_mocked(db_path: Path) -> None:
    layer = FeedValidationLayer(OperationsRepository(db_path))
    with patch("bot.operations.feed_validation.fetch_feed_items") as mock_fetch:
        from bot.ingestion.rss import NewsItem

        mock_fetch.return_value = [
            NewsItem(title="Test", link="https://a.com/1", published=None, source="x"),
            NewsItem(title="Test", link="https://a.com/1", published=None, source="x"),
        ]
        result = layer.validate_feed("https://example.com/feed", source_name="test")
        assert result.items_fetched == 2
        assert result.duplicates >= 1


def test_ergonomics_triage(db_path: Path) -> None:
    erg = OperationalErgonomics(OperationsRepository(db_path))
    erg.ingest_alert(alert_key="a1", category="misinformation", title="Test alert", detail={"x": 1})
    triage = erg.triage_open()
    assert triage
    assert triage[0].priority >= 80


def test_storage_snapshot(db_path: Path) -> None:
    ops = build_operations_platform(db_path, node_id="t", region="eu")
    counts = ops.storage.snapshot_tables()
    assert isinstance(counts, dict)


def test_certification_slo_gates(db_path: Path) -> None:
    cert = ProductionReadinessCertification(OperationsRepository(db_path))

    async def _run():
        report = await cert.run(
            signals={
                "queue_backlog": 10,
                "epistemic_stability": 0.9,
                "mesh_health": 0.85,
                "replay_divergence": 0.05,
                "storage_growth_mb_day": 5,
            },
        )
        assert report.passed
        assert len(report.gates) >= 5

    asyncio.run(_run())


def test_operations_tick(db_path: Path) -> None:
    ops = build_operations_platform(db_path, node_id="t", region="eu")

    async def _run():
        report = await ops.operational_tick(
            signals={"health_score": 0.9, "queue_backlog": 5, "epistemic_stability": 0.8},
            run_feed_validation=False,
        )
        assert "operator_alerts_open" in report

    asyncio.run(_run())


def test_archaeology_bundle(db_path: Path) -> None:
    ops = build_operations_platform(db_path, node_id="t", region="eu")
    bid = ops.archaeology.capture(
        "incident-1",
        timeline=[{"at": "t0", "event": "spike"}],
        cognitive_state={"epistemic_stability": 0.5},
    )
    report = ops.archaeology.export_report(bid)
    assert "incident-1" in report
