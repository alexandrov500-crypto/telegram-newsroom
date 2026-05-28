"""Event-driven pipeline state engine."""

from __future__ import annotations

import pytest

from app.dependency_state import DependencyStatus, get_dependency_state, reset_dependency_state
from app.openai_circuit import get_openai_circuit, reset_openai_circuit_for_tests
from app.state.pipeline_state_engine import (
    PipelineExecutionMode,
    PipelineStateContext,
    evaluate_pipeline_state,
    should_run_summarize,
)


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_dependency_state()
    reset_openai_circuit_for_tests()
    yield
    reset_dependency_state()
    reset_openai_circuit_for_tests()


def test_degraded_openai_does_not_block_when_backlog() -> None:
    deps = get_dependency_state()
    deps.set_dependency("openai", status=DependencyStatus.DEGRADED, detail="startup")
    get_openai_circuit().force_open("test")

    ctx = PipelineStateContext(
        raw_unprocessed=50,
        circuit_state="open",
        circuit_allows=False,
        openai_status="degraded",
        fallback_available=True,
        backlog_size=50,
        last_successful_ai_sec_ago=None,
        last_successful_tick_sec_ago=10.0,
        summarizer_health="degraded",
    )
    d = evaluate_pipeline_state(ctx)
    assert d.execution_active is True
    assert d.summarize_enabled is True
    assert d.use_fallback is True
    assert d.degraded_blocks_execution is False
    assert d.mode == PipelineExecutionMode.FALLBACK_BACKLOG


def test_degraded_idle_without_backlog_is_idle_not_stuck_false() -> None:
    ctx = PipelineStateContext(
        raw_unprocessed=0,
        circuit_state="closed",
        circuit_allows=True,
        openai_status="degraded",
        fallback_available=True,
        backlog_size=0,
        last_successful_ai_sec_ago=None,
        last_successful_tick_sec_ago=None,
        summarizer_health="degraded",
        fallback_success_recent=False,
    )
    d = evaluate_pipeline_state(ctx)
    assert d.mode == PipelineExecutionMode.BLOCKED_CIRCUIT
    assert d.execution_active is False
    assert d.degraded_blocks_execution is False


def test_recent_fallback_success_reenables_execution() -> None:
    ctx = PipelineStateContext(
        raw_unprocessed=0,
        circuit_state="closed",
        circuit_allows=True,
        openai_status="degraded",
        fallback_available=True,
        backlog_size=0,
        last_successful_ai_sec_ago=30.0,
        last_successful_tick_sec_ago=5.0,
        summarizer_health="degraded",
        fallback_success_recent=True,
    )
    d = evaluate_pipeline_state(ctx)
    assert d.execution_active is True
    assert d.mode == PipelineExecutionMode.ACTIVE


def test_should_run_summarize_with_backlog() -> None:
    ctx = PipelineStateContext(
        raw_unprocessed=10,
        circuit_state="open",
        circuit_allows=False,
        openai_status="degraded",
        fallback_available=True,
        backlog_size=10,
        last_successful_ai_sec_ago=None,
        last_successful_tick_sec_ago=None,
        summarizer_health="degraded",
    )
    assert should_run_summarize(ctx) is True
