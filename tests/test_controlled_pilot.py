from __future__ import annotations

import asyncio
from pathlib import Path

from bot.live_ops.channel_settings import LiveMode
from bot.live_ops.controlled_factory import build_controlled_live_stack
from bot.live_ops.publish_trace import PublishTraceStore
from bot.live_ops.source_quarantine import SourceQuarantine
from bot.live_ops.metrics_snapshot import LiveMetricsSnapshotter
from bot.live_ops.startup_validation import ControlledLiveStartupValidator
from bot.live_ops.channel_settings import ControlledLiveSettings
from bot.storage.db import init_database


def test_publish_trace_roundtrip(tmp_path: Path) -> None:
    init_database(tmp_path / "p1.db")
    store = PublishTraceStore(tmp_path / "p1.db")
    trace = store.record_decision(
        pending_news_id=42,
        mode="canary",
        channel="-1001",
        source="reuters",
        cluster_id=7,
        confidence_score=0.9,
        trust_score=0.88,
        safety_score=0.94,
        guard_result="pass",
        hold_reason=None,
        operator_override=False,
        published=False,
    )
    assert trace["post_id"] == "42"
    store.update_published(42, published=True, guard_result="published")
    got = store.get(42)
    assert got is not None
    assert got["published"] is True


def test_source_quarantine_after_threshold(tmp_path: Path) -> None:
    init_database(tmp_path / "p2.db")
    q = SourceQuarantine(tmp_path / "p2.db", bad_threshold=3, cooldown_hours=6)
    for _ in range(3):
        q.record_bad_post("reuters")
    blocked, mode = q.is_quarantined("reuters")
    assert blocked
    assert mode in ("shadow", "block")


def test_metrics_snapshot(tmp_path: Path) -> None:
    init_database(tmp_path / "p3.db")
    snap = LiveMetricsSnapshotter(tmp_path / "p3.db", interval_sec=0)
    out = snap.save({"published_last_hour": 2, "channel_health": 0.9})
    assert out["published_last_hour"] == 2
    assert snap.latest() is not None


def test_startup_blocks_autonomous(tmp_path: Path) -> None:
    init_database(tmp_path / "p4.db")
    settings = ControlledLiveSettings(
        enabled=True,
        live_mode=LiveMode.AUTONOMOUS_LIVE,
    )
    validator = ControlledLiveStartupValidator(tmp_path / "p4.db", settings)

    async def _run() -> None:
        report = await validator.validate()
        assert not report.passed
        assert report.forced_shadow

    asyncio.run(_run())


def test_coordinator_startup(tmp_path: Path) -> None:
    async def _run() -> None:
        init_database(tmp_path / "p5.db")
        coord = build_controlled_live_stack(tmp_path / "p5.db")
        out = await coord.startup()
        assert "passed" in out

    asyncio.run(_run())
