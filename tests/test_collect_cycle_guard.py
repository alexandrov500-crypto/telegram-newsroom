"""Collect cycle guard — stall detection and timeout config."""

from __future__ import annotations

import asyncio
import os

import pytest

from app.runtime.collect_cycle_guard import (
    begin_collect,
    collect_timeout_sec,
    end_collect,
    reset_collect_cycle_guard_for_tests,
    snapshot,
)


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_collect_cycle_guard_for_tests()
    yield
    reset_collect_cycle_guard_for_tests()


def test_collect_snapshot_idle() -> None:
    assert snapshot()["collect_in_progress"] is False


def test_collect_in_progress_snapshot() -> None:
    begin_collect(tick_id="t-1")
    snap = snapshot()
    assert snap["collect_in_progress"] is True
    assert snap["collect_tick_id"] == "t-1"
    end_collect(success=True)


def test_pre_production_default_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COLLECT_CYCLE_TIMEOUT_SEC", raising=False)
    monkeypatch.setenv("PRE_PRODUCTION_VALIDATION_MODE", "true")
    assert collect_timeout_sec() == 300.0


def test_collect_timeout_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COLLECT_CYCLE_TIMEOUT_SEC", "90")
    assert collect_timeout_sec() == 90.0


def test_collect_body_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COLLECT_CYCLE_TIMEOUT_SEC", "0.2")

    async def slow() -> None:
        await asyncio.sleep(2.0)

    begin_collect()

    async def run() -> None:
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(slow(), timeout=collect_timeout_sec())

    asyncio.run(run())
    end_collect(success=False, error="timeout")
