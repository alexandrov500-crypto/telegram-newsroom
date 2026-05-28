from __future__ import annotations

import time

import pytest

from app.ops.control_plane import (
    disable_ingestion,
    emergency_halt,
    enable_ingestion,
    init_ops_state_store,
    ops_control_snapshot,
    resume_normal_ops,
    set_slow_mode,
)
from app.ops.control_plane.auto_controller import evaluate_auto_ops
from app.ops.control_plane.guards import (
    effective_pipeline_interval_minutes,
    emergency_halt_active,
    fast_lane_allowed,
    ingestion_allowed,
    pipeline_tick_allowed,
    publish_allowed_now,
    should_drop_message,
)
from app.ops.control_plane.state import reset_ops_state_store_for_tests


@pytest.fixture(autouse=True)
def _reset_ops():
    reset_ops_state_store_for_tests()
    init_ops_state_store(None)
    yield
    reset_ops_state_store_for_tests()


def test_emergency_halt_blocks_all_lanes():
    emergency_halt(reason="test")
    assert emergency_halt_active()
    assert not ingestion_allowed()
    assert not fast_lane_allowed()
    assert should_drop_message(lane="fast")
    assert should_drop_message(lane="standard")


def test_slow_mode_triples_pipeline_interval():
    set_slow_mode(True, reason="burst")
    assert effective_pipeline_interval_minutes(10) == 30
    set_slow_mode(False, reason="stable")
    assert effective_pipeline_interval_minutes(10) == 10


def test_disable_ingestion_without_halt():
    disable_ingestion(reason="operator")
    assert not ingestion_allowed()
    assert not should_drop_message()
    enable_ingestion(reason="operator")
    assert ingestion_allowed()


def test_pipeline_tick_throttle_under_slow_mode():
    from app.ops.control_plane.state import get_ops_store

    set_slow_mode(True, reason="load")
    get_ops_store().note_pipeline_tick(unix=time.time())
    allowed, reason = pipeline_tick_allowed(base_interval_minutes=5)
    assert not allowed
    assert "slow_mode" in reason


def test_fast_lane_ignores_slow_mode():
    from app.ops.control_plane.api import enable_fast_lane

    enable_fast_lane(reason="test")
    set_slow_mode(True, reason="load")
    assert fast_lane_allowed()


def test_resume_normal_ops():
    emergency_halt(reason="incident")
    resume_normal_ops(reason="cleared")
    snap = ops_control_snapshot()
    assert snap["emergency_halt"] is False
    assert snap["ingestion_enabled"] is True
    assert snap["slow_mode"] is False


def test_publish_rate_limit():
    from app.ops.control_plane.api import set_publish_rate_limit
    from app.ops.control_plane.state import get_ops_store

    set_publish_rate_limit(2, reason="test")
    store = get_ops_store()
    now = time.time()
    store.record_publish_attempt(unix=now)
    store.record_publish_attempt(unix=now)
    ok, reason = publish_allowed_now()
    assert not ok
    assert reason == "publish_rate_limit"


def test_auto_controller_disabled_by_env(monkeypatch):
    monkeypatch.setenv("OPS_AUTO_CONTROLLER", "false")
    assert evaluate_auto_ops().get("applied") is False
