"""Final staging regression: health, desk thresholds, publish trace, replay."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.editorial.desk_filter import evaluate_desk_filter
from app.editorial.desk_starvation import DeskThresholdContext
from app.editorial.desk_thresholds import category_min_publish_score, category_thresholds_snapshot
from app.editorial.replay_simulation import replay_rejected_items
from app.editorial.scoring_engine import EditorialScore
from publisher.publish_trace import log_publish_trace


def _escore(**kw) -> EditorialScore:
    defaults = dict(
        credibility_score=0.7,
        impact_score=0.5,
        relevance_score=0.4,
        urgency_score=0.3,
        breaking_score=0.1,
        final_priority_score=0.55,
        lane="standard",
        is_breaking=False,
        reason="test",
    )
    defaults.update(kw)
    return EditorialScore(**defaults)


def test_category_thresholds_monotonic_under_starvation():
    normal = DeskThresholdContext(
        base_min_publish_score=45.0,
        effective_min_publish_score=45.0,
        lower_priority_score=32.0,
        min_macro_market_score=30.0,
        relevance_floor=0.28,
        starvation_active=False,
        publish_starvation_detected=False,
        hours_since_publish=1.0,
        score_reduction=0.0,
    )
    starved = DeskThresholdContext(
        base_min_publish_score=45.0,
        effective_min_publish_score=39.0,
        lower_priority_score=32.0,
        min_macro_market_score=30.0,
        relevance_floor=0.22,
        starvation_active=True,
        publish_starvation_detected=True,
        hours_since_publish=8.0,
        score_reduction=6.0,
    )
    assert category_min_publish_score("market", normal) >= category_min_publish_score("market", starved)
    snap = category_thresholds_snapshot(starved)
    assert snap["breaking"] >= snap["market"]


def test_desk_reject_has_reason_code():
    text = (
        "Срочно узнай секрет биткоина по слухам без подтверждения — шокирующая новость "
        "для всех инвесторов прямо сейчас."
    )
    decision = evaluate_desk_filter(text, _escore(credibility_score=0.4, relevance_score=0.2))
    assert not decision.publish
    assert decision.reason_code.startswith("desk.")


def test_staging_health_snapshot_shape():
    from app.observability.staging_health import staging_health_snapshot

    snap = staging_health_snapshot()
    assert "pipeline" in snap
    assert "editorial" in snap
    assert "publishing" in snap
    assert "alerts" in snap
    assert isinstance(snap["alerts"], list)


def test_publish_trace_log_event(caplog):
    import logging

    with caplog.at_level(logging.INFO):
        log_publish_trace(
            event="started",
            draft_id=99,
            publish_attempt=2,
            channel_id=-100123,
            idempotency_key="draft:99",
        )
    joined = " ".join(getattr(r, "message", str(r)) for r in caplog.records)
    assert "publish.trace" in joined or "draft_id" in joined


def test_replay_simulation_empty_runtime(tmp_path):
    out = replay_rejected_items(str(tmp_path), limit=5)
    assert out["count"] == 0


def test_publish_attempt_from_failed_queue():
    import asyncio

    from publisher.publish_service import _publish_attempt_number

    row = MagicMock()
    row.retry_count = 2

    async def _run() -> int:
        with patch(
            "db.reliability_repository.get_failed_draft_row",
            return_value=row,
        ):
            return await _publish_attempt_number(7)

    assert asyncio.run(_run()) == 3


def test_publish_retry_flow_terminal_pattern():
    from app.reliability.failed_draft_recovery import is_publish_failure_retryable

    assert is_publish_failure_retryable(reason="Connection timeout")
    assert not is_publish_failure_retryable(reason="cadence_blocked_publish")
    assert not is_publish_failure_retryable(reason="desk_reject quality_below")


def test_health_payload_includes_staging():
    from app.dependency_state import reset_dependency_state, get_dependency_state

    reset_dependency_state()
    payload = get_dependency_state().health_payload()
    assert "staging" in payload
