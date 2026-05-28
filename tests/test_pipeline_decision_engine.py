"""Pipeline decision engine — deterministic execution authority."""

from __future__ import annotations

import pytest

from app.state.pipeline_decision_engine import (
    PipelineDecisionMode,
    PipelineDecisionContext,
    PipelineNextAction,
    make_pipeline_decision,
)


def test_backlog_never_blocked_by_degraded_only() -> None:
    ctx = PipelineDecisionContext(
        raw_unprocessed=42,
        circuit_state="open",
        circuit_allows=False,
        openai_status="degraded",
        summarizer_health="degraded",
        fallback_available=True,
        backlog_size=42,
        last_successful_tick_sec_ago=5.0,
        last_successful_ai_sec_ago=None,
        retry_pressure=0.1,
        system_load=0.2,
    )
    d = make_pipeline_decision(ctx)
    assert d.should_execute is True
    assert d.mode == PipelineDecisionMode.FALLBACK
    assert d.next_action == PipelineNextAction.SUMMARIZE
    assert d.use_fallback is True
    assert "degraded_observability_only" in str(d.observability_trace.get("reasoning_chain"))


def test_idle_degraded_no_backlog_explicit_skip() -> None:
    ctx = PipelineDecisionContext(
        raw_unprocessed=0,
        circuit_state="closed",
        circuit_allows=True,
        openai_status="degraded",
        summarizer_health="degraded",
        fallback_available=True,
        backlog_size=0,
        last_successful_tick_sec_ago=None,
        last_successful_ai_sec_ago=None,
    )
    d = make_pipeline_decision(ctx)
    assert d.should_execute is False
    assert d.next_action == PipelineNextAction.SKIP


def test_minimal_backlog_force_draft() -> None:
    ctx = PipelineDecisionContext(
        raw_unprocessed=5,
        circuit_state="closed",
        circuit_allows=True,
        openai_status="degraded",
        summarizer_health="degraded",
        fallback_available=True,
        backlog_size=5,
        last_successful_tick_sec_ago=1.0,
        last_successful_ai_sec_ago=None,
        minimal_mode=True,
    )
    d = make_pipeline_decision(ctx)
    assert d.should_execute is True
    assert d.next_action == PipelineNextAction.FORCE_DRAFT
