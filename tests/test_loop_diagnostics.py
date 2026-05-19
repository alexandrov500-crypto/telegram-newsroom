from __future__ import annotations

import asyncio

import pytest

from bot.observability.loop_diagnostics import (
    collect_lag_context,
    record_event_loop_lag,
    timed_async_job,
    track_sync_db,
)


def test_record_event_loop_lag_updates_stats() -> None:
    record_event_loop_lag(0.05)
    record_event_loop_lag(2.5)
    ctx = collect_lag_context()
    assert ctx["lag_max_sec"] >= 2.5
    assert ctx["lag_avg_sec"] > 0


def test_timed_async_job_records_duration() -> None:
    async def _run() -> None:
        async with timed_async_job("test_job"):
            await asyncio.sleep(0.001)

    asyncio.run(_run())
    ctx = collect_lag_context()
    assert ctx.get("current_job") is None


def test_track_sync_db_fast_no_slow_count() -> None:
    from bot.observability.loop_diagnostics import get_loop_diagnostics

    before = get_loop_diagnostics().slow_db_operation_count
    with track_sync_db("unit_test_fast"):
        pass
    after = get_loop_diagnostics().slow_db_operation_count
    assert after == before
