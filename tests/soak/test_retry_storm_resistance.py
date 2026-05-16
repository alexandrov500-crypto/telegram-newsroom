"""Retry storm boundedness under synthetic load."""

from __future__ import annotations

import asyncio

from tests.conftest import minimal_test_settings
from workers import state as worker_state
from workers.retry import build_policy_from_settings


def test_retry_burst_bounded_in_window() -> None:
    async def body() -> None:
        worker_state.reset_worker_runtime_state_for_tests()
        s = minimal_test_settings(runtime_retry_storm_count=5, runtime_retry_storm_window_sec=60.0)
        for _ in range(20):
            await worker_state.on_retry()
        diag = await worker_state.collect_runtime_diag(s)
        assert int(diag["retry_burst_window"]) == 20
        assert int(diag["retry_burst_window"]) <= 512

    asyncio.run(body())


def test_retry_policy_never_unbounded_delay() -> None:
    s = minimal_test_settings()
    p = build_policy_from_settings(s, envelope_attempt=0)
    for i in range(30):
        assert p.next_delay_sec(i) <= 336.0
    assert p.exhausted(p.max_attempts)


def test_retry_storm_recovers_counters_reset() -> None:
    worker_state.reset_worker_runtime_state_for_tests()
    snap = worker_state.runtime_counters_snapshot()
    assert snap["retry_total"] == 0
