"""Telegram connectivity health snapshot."""

from __future__ import annotations

from app.dependency_state import DependencyStatus, get_dependency_state, reset_dependency_state
from app.runtime.collect_cycle_guard import begin_collect, reset_collect_cycle_guard_for_tests
from app.runtime.telegram_connectivity import build_telegram_connectivity_snapshot


def test_connectivity_snapshot_fields() -> None:
    reset_dependency_state()
    reset_collect_cycle_guard_for_tests()
    snap = build_telegram_connectivity_snapshot()
    assert "bot_api_status" in snap
    assert "polling_retry_count" in snap
    assert snap["collect_cycle"]["collect_in_progress"] is False


def test_stalled_collect_marks_dc_unreachable() -> None:
    reset_dependency_state()
    reset_collect_cycle_guard_for_tests()
    deps = get_dependency_state()
    deps.telegram_api.status = DependencyStatus.HEALTHY
    begin_collect(tick_id="stall-test")
    import time

    from app.runtime import collect_cycle_guard as cg

    cg._started_mono = time.monotonic() - 500.0  # noqa: SLF001 — test stall
    snap = build_telegram_connectivity_snapshot()
    assert snap["collect_cycle"]["collect_stalled"] is True
    assert snap["dc_reachable"] is False
