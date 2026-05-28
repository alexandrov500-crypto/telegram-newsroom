"""End-to-end execution integrity: wrapper, trace, decision engine, no silent ticks."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.dependency_state import reset_dependency_state
from app.openai_circuit import reset_openai_circuit_for_tests
from app.state.pipeline_execution_registry import (
    FORBIDDEN_DIRECT_CALLS,
    validate_execution_origin,
)
from app.state.pipeline_execution_wrapper import (
    execute_pipeline_step,
    execute_pipeline_step_async,
    pipeline_evaluation_only,
    require_pipeline_wrapper_active,
)
from scheduler.jobs import build_pipeline_context, run_pipeline
from scheduler.pipeline_lock import get_pipeline_lock
from scheduler.runtime_context import set_pipeline_context
from tests.conftest import minimal_test_settings
from utils.metrics import reset_metrics


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_metrics()
    reset_dependency_state()
    reset_openai_circuit_for_tests()
    set_pipeline_context(None)
    monkeypatch.setattr(
        "app.ops.runtime.pipeline_gate.require_processing_or_skip",
        lambda **_: True,
    )
    monkeypatch.setattr(
        "app.ops.control_plane.guards.pipeline_tick_allowed",
        lambda **_: (True, ""),
    )
    yield
    reset_metrics()
    set_pipeline_context(None)


def test_forbidden_impls_registered() -> None:
    assert "_summarize_step_impl" in FORBIDDEN_DIRECT_CALLS


def test_direct_impl_call_fails_origin_validation() -> None:
    async def _bad():
        from scheduler.jobs import _summarize_step_impl
        from scheduler.runtime_context import PipelineContext
        from tests.conftest import minimal_test_settings

        ctx = PipelineContext(
            settings=minimal_test_settings(),
            bot=MagicMock(),
            openai=MagicMock(),
        )
        await _summarize_step_impl(ctx)

    with pytest.raises(RuntimeError, match="PIPELINE BYPASS"):
        import os

        os.environ["PIPELINE_EXECUTION_ENFORCEMENT"] = "strict"
        try:
            asyncio.run(_bad())
        finally:
            os.environ.pop("PIPELINE_EXECUTION_ENFORCEMENT", None)


def test_wrapper_produces_full_trace_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[dict] = []

    def _cap(_logger, event, **kw):
        if event in ("PIPELINE_EXECUTION_TRACE", "PIPELINE_DECISION_TRACE"):
            events.append({"event": event, **kw})

    monkeypatch.setattr("app.state.pipeline_execution_wrapper.log_event", _cap)
    monkeypatch.setattr("app.state.pipeline_decision_engine.log_event", _cap)

    ctx = build_pipeline_context(
        minimal_test_settings(),
        MagicMock(),
        MagicMock(),
    )
    ran = {"ok": False}

    async def _fn():
        ran["ok"] = True
        return "done"

    asyncio.run(
        execute_pipeline_step_async(ctx, "collect", _fn, require_should_execute=False)
    )
    assert ran["ok"]
    phases = [e.get("phase") for e in events if e.get("event") == "PIPELINE_EXECUTION_TRACE"]
    assert "wrapper_entry" in phases
    assert "wrapper_exit" in phases
    assert any(e.get("decision_engine_called") for e in events if e.get("event") == "PIPELINE_EXECUTION_TRACE")
    assert getattr(ctx, "pipeline_trace_id", "")


def test_tick_through_wrapper_not_silent(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    async def setup_db() -> str:
        from db.session import close_db, init_db

        await close_db()
        url = f"sqlite+aiosqlite:///{tmp_path / 'integrity.db'}"
        await init_db(url)
        return url

    url = asyncio.run(setup_db())

    async def body() -> None:
        settings = minimal_test_settings(database_url=url)
        bot = MagicMock()
        bot.session = MagicMock()
        bot.session.close = AsyncMock()
        openai = MagicMock()
        openai.close = AsyncMock()
        ctx = build_pipeline_context(settings, bot, openai)

        async def fake_collect(c):
            c.tick_timings["collect_sec"] = 0.01

        async def fake_summarize(c):
            c.tick_summarize_idle_reason = "explicit_reject:test"
            c.last_cluster_size = 0

        monkeypatch.setattr("scheduler.jobs._collect_step", fake_collect)
        monkeypatch.setattr("scheduler.jobs._summarize_step_impl", fake_summarize)

        await run_pipeline(ctx)
        assert ctx.last_scheduler_wall_sec > 0
        assert ctx.tick_summarize_idle_reason.startswith("explicit_reject")

    asyncio.run(body())


def test_evaluation_only_skips_stack_enforcement() -> None:
    with pipeline_evaluation_only():
        require_pipeline_wrapper_active("health_probe")
    verdict = validate_execution_origin("health_probe")
    # outside wrapper without evaluation_only may be disallowed
    assert verdict.callee == "health_probe"
