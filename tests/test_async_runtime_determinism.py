"""Async runtime orchestrator: generation, dedupe, trace, cancellation."""

from __future__ import annotations

import asyncio

import pytest

from app.runtime.task_orchestrator import (
    active_tasks,
    bump_runtime_generation,
    create_traced_task,
    reset_task_orchestrator_for_tests,
    strict_trace_mode,
)
from app.runtime.task_watchdog import reset_task_watchdog_for_tests


@pytest.fixture(autouse=True)
def _reset_orchestrator() -> None:
    reset_task_orchestrator_for_tests()
    reset_task_watchdog_for_tests()
    yield
    reset_task_orchestrator_for_tests()
    reset_task_watchdog_for_tests()


def _capture_events(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    events: list[dict] = []

    def _cap(_logger, event, **kw):
        events.append({"event": event, **kw})

    monkeypatch.setattr("app.runtime.task_orchestrator.log_event", _cap)
    return events


def test_stale_generation_aborts_task(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run() -> None:
        events = _capture_events(monkeypatch)
        ran = {"ok": False}

        async def _body() -> None:
            ran["ok"] = True

        task = create_traced_task(
            "stale-test",
            _body(),
            trace_id="trace-stale",
            owner="test",
            metadata={"task_type": "test"},
        )
        assert task is not None
        bump_runtime_generation()
        await task
        assert ran["ok"] is False
        assert any(e.get("event") == "TASK_STALE_GENERATION_ABORT" for e in events)

    asyncio.run(_run())


def test_duplicate_publish_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run() -> None:
        events = _capture_events(monkeypatch)
        gate = asyncio.Event()

        async def _slow() -> None:
            await gate.wait()

        t1 = create_traced_task(
            "publish-draft",
            _slow(),
            trace_id="t-publish-1",
            owner="test",
            metadata={"task_type": "publish", "draft_id": 42},
        )
        t2 = create_traced_task(
            "publish-draft-2",
            _slow(),
            trace_id="t-publish-2",
            owner="test",
            metadata={"task_type": "publish", "draft_id": 42},
        )
        assert t1 is not None
        assert t2 is None
        assert any(e.get("event") == "TASK_DUPLICATE_BLOCKED" for e in events)
        gate.set()
        await t1

    asyncio.run(_run())


def test_duplicate_phase_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run() -> None:
        events = _capture_events(monkeypatch)
        hold = asyncio.Event()

        async def _phase() -> None:
            await hold.wait()

        t1 = create_traced_task(
            "summarize-phase",
            _phase(),
            trace_id="t-sum-1",
            owner="test",
            metadata={"phase": "summarize"},
        )
        t2 = create_traced_task(
            "summarize-phase-2",
            _phase(),
            trace_id="t-sum-2",
            owner="test",
            metadata={"phase": "summarize"},
        )
        assert t1 is not None
        assert t2 is None
        assert any(e.get("event") == "TASK_DUPLICATE_BLOCKED" for e in events)
        hold.set()
        await t1

    asyncio.run(_run())


def test_cancellation_emits_trace(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run() -> None:
        events = _capture_events(monkeypatch)

        async def _wait() -> None:
            await asyncio.sleep(3600)

        task = create_traced_task(
            "cancel-me",
            _wait(),
            trace_id="t-cancel",
            owner="test",
            metadata={"task_type": "test"},
        )
        assert task is not None
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert any(e.get("event") == "TASK_CANCELLED_TRACE" for e in events)

    asyncio.run(_run())


def test_registry_tasks_have_trace_id() -> None:
    async def _run() -> None:
        async def _quick() -> str:
            return "ok"

        task = create_traced_task(
            "trace-registry",
            _quick(),
            trace_id="trace-reg-1",
            owner="test",
        )
        assert task is not None
        assert all(r.trace_id for r in active_tasks())
        await task

    asyncio.run(_run())


def test_strict_trace_mode_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ASYNC_RUNTIME_STRICT_TRACE", "true")
    assert strict_trace_mode() is True

    async def _noop() -> None:
        return None

    async def _run() -> None:
        task = create_traced_task("no-trace", _noop(), trace_id=None, owner="test")
        assert task is None

    asyncio.run(_run())
