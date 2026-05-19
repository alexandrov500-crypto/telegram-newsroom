from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.operator_console.aggregation import NotificationAggregator

EventAggregator = NotificationAggregator
from bot.operator_console.approval_queue import ApprovalQueueItem, SmartApprovalQueue
from bot.operator_console.fatigue import FatigueGuard
from bot.operator_console.hub import OperatorSignalHub
from bot.operator_console.incidents import IncidentCorrelator
from bot.operator_console.scoring import compute_ops_health
from bot.operator_console.severity import AlertLevel, score_contradiction_burst
from bot.operator_console.console import OperatorTelegramConsole
from bot.settings import BotSettings


def test_aggregator_contradiction_summary() -> None:
    agg = EventAggregator(default_window_sec=0.01)
    for _ in range(5):
        agg.record("contradiction", {"subject_type": "geopolitical", "explanation": "policy"})
    import time

    time.sleep(0.02)
    flushed = agg.flush("contradiction")
    assert flushed is not None
    md, agg_id, n, _sev = flushed
    assert n == 5
    assert "CONTRADICTION SUMMARY" in md
    assert agg_id


def test_fatigue_never_suppresses_critical() -> None:
    guard = FatigueGuard(max_messages_per_hour=1, max_alerts_per_hour=1)
    for _ in range(10):
        guard.record_send(is_alert=True)
    assert guard.should_suppress(AlertLevel.CRITICAL) is False
    assert guard.should_suppress(AlertLevel.INFO) is True


def test_incident_correlation_threads() -> None:
    corr = IncidentCorrelator()
    t1 = corr.correlate(
        "contradiction",
        title="Burst",
        detail="open=12",
        severity=AlertLevel.WARNING,
        replay_ref="evt_1",
    )
    t2 = corr.correlate(
        "contradiction",
        title="Burst",
        detail="open=14",
        severity=AlertLevel.WARNING,
    )
    assert t1.thread_id == t2.thread_id
    assert len(t2.events) >= 2


def test_ops_health_deterministic() -> None:
    a = compute_ops_health(queue_backlog=100, open_contradictions=5, fatigue_score=0.2)
    b = compute_ops_health(queue_backlog=100, open_contradictions=5, fatigue_score=0.2)
    assert a.overall == b.overall
    assert a.trend in ("stable", "healthy", "degrading")


def test_approval_queue_priority_order() -> None:
    q = SmartApprovalQueue()
    q.enqueue(
        ApprovalQueueItem(
            sort_index=-0.5,
            news_id=1,
            headline="low",
            summary="",
            confidence=0.6,
            epistemic_stability=0.7,
            contradiction_exposure=0,
            misinfo_risk=0.1,
            source_diversity=1,
            replay_id="evt_1",
        )
    )
    q.enqueue(
        ApprovalQueueItem(
            sort_index=-0.9,
            news_id=2,
            headline="high",
            summary="",
            confidence=0.9,
            epistemic_stability=0.9,
            contradiction_exposure=0,
            misinfo_risk=0.0,
            source_diversity=2,
            replay_id="evt_2",
        )
    )
    batch = q.drain_for_digest(1)
    assert batch[0].news_id == 2


def test_severity_contradiction_escalation() -> None:
    assert score_contradiction_burst(30, delta=20) == AlertLevel.CRITICAL
    assert score_contradiction_burst(10, delta=2) == AlertLevel.NOTICE


def test_clamp_lines() -> None:
    from bot.operator_console.formatting import clamp_lines

    text = "\n".join(f"line {i}" for i in range(20))
    assert len(clamp_lines(text, max_lines=10).split("\n")) <= 10


def test_explainability_compact() -> None:
    from bot.operator_console.explainability import why_flagged_compact

    item = type("Item", (), {"id": 1, "priority_score": 0.8})()
    out = why_flagged_compact(item=item)
    assert "evt_1" in out
    assert len(out.split("\n")) <= 8


def test_hub_aggregates_duplicate_ingest() -> None:
    async def _run() -> None:
        bot = AsyncMock()
        settings = BotSettings(
            TELEGRAM_BOT_TOKEN="x" * 20,
            TELEGRAM_LIVE_INGEST_ENABLED=True,
            TELEGRAM_OPERATOR_CHAT_ID=-100123,
        )
        console = OperatorTelegramConsole(bot, settings)
        await console.notify_ingest(
            source="reuters",
            language="en",
            headline="Dup",
            outcome="duplicate",
            confidence=0.5,
            cluster_id=1,
            news_id=1,
            priority=0.9,
            duplicate=True,
        )
        bot.send_message.assert_not_called()
        assert console.hub._aggregator._buffers.get("ingest") is not None

    asyncio.run(_run())
