from __future__ import annotations

import os

from bot.observability.loop_health import (
    LoopIterationStats,
    is_autonomous_passive_mode,
    record_autonomous_iteration,
    record_rss_iteration,
    snapshot,
)
from bot.operations.recovery_cooldown import RecoveryCooldown


def test_record_rss_iteration() -> None:
    record_rss_iteration(
        LoopIterationStats(
            loop_name="rss-ingestion",
            iteration_duration=0.5,
            feed_count=3,
            article_count=10,
            network_duration=0.3,
            db_write_duration=0.2,
        ),
    )
    snap = snapshot()
    assert snap["rss_loop_duration_max"] >= 0.5
    assert snap["last_rss"]["feed_count"] == 3


def test_autonomous_passive_canary_env(monkeypatch) -> None:
    monkeypatch.setenv("LIVE_MODE", "canary")
    monkeypatch.delenv("PILOT_AUTONOMOUS_PASSIVE", raising=False)
    assert is_autonomous_passive_mode() is True


def test_recovery_cooldown() -> None:
    cd = RecoveryCooldown(min_interval_sec=60.0)
    assert cd.allow("loop_stalled:rss-ingestion") is True
    assert cd.allow("loop_stalled:rss-ingestion") is False


def test_autonomous_passive_iteration() -> None:
    record_autonomous_iteration(
        LoopIterationStats(
            loop_name="autonomous-runtime",
            task_duration=0.02,
            passive=True,
        ),
    )
    snap = snapshot()
    assert snap["autonomous_passive"] is True
