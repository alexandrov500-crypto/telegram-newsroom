"""Runtime guards — emergency halt, ingestion pause, slow mode, publish limits."""

from __future__ import annotations

import logging
import time
from typing import Any

from app.ops.control_plane.state import OpsState, get_ops_state, get_ops_store

logger = logging.getLogger(__name__)

_SLOW_MODE_MULTIPLIER = 3


def emergency_halt_active() -> bool:
    return get_ops_state().emergency_halt


def ingestion_allowed() -> bool:
    st = get_ops_state()
    return st.ingestion_enabled and not st.emergency_halt


def fast_lane_allowed() -> bool:
    """Fast lane ignores slow_mode; respects emergency_halt and fast_lane_enabled."""
    st = get_ops_state()
    if st.emergency_halt:
        return False
    return st.fast_lane_enabled


def standard_lane_allowed() -> bool:
    st = get_ops_state()
    if st.emergency_halt:
        return False
    if st.fast_lane_only:
        return False
    return True


def should_drop_message(*, lane: str | None = None) -> bool:
    """Absolute kill switch — drops all lanes including FAST."""
    if not emergency_halt_active():
        return False
    logger.info("[OPS] drop msg lane=%s reason=emergency_halt", lane or "any")
    return True


def effective_pipeline_interval_minutes(base_minutes: int) -> int:
    import math
    import os

    st = get_ops_state()
    base = max(1, int(base_minutes))
    effective = base * _SLOW_MODE_MULTIPLIER if st.slow_mode else base
    try:
        from app.observability.runtime_protection import pipeline_interval_multiplier

        mult = pipeline_interval_multiplier(os.getenv("RUNTIME_STATE_DIR", "var/runtime"))
        if mult > 1.0:
            effective = max(base, int(math.ceil(effective * mult)))
    except Exception:
        pass
    return effective


def pipeline_tick_allowed(*, base_interval_minutes: int) -> tuple[bool, str]:
    """Throttle scheduler ticks when slow_mode without APScheduler reschedule."""
    st = get_ops_state()
    if st.emergency_halt:
        return False, "emergency_halt"
    effective = effective_pipeline_interval_minutes(base_interval_minutes)
    last = get_ops_store().last_pipeline_tick_unix()
    if last <= 0:
        return True, "first_tick"
    elapsed_min = (time.time() - last) / 60.0
    # Small grace so APScheduler interval and throttle do not miss by seconds (14.9<15 → 30min gap).
    if elapsed_min + (30.0 / 60.0) < effective:
        return False, f"slow_mode_throttle:{elapsed_min:.1f}<{effective}min"
    return True, "ok"


def queue_depth_over_cap(*, fast: int, standard: int, slow: int) -> bool:
    st = get_ops_state()
    return (fast + standard + slow) >= st.max_queue_depth


def publish_allowed_now() -> tuple[bool, str]:
    st = get_ops_state()
    if st.emergency_halt:
        return False, "emergency_halt"
    if get_ops_store().publish_rate_limited():
        return False, "publish_rate_limit"
    return True, "ok"


def log_guard_skip(component: str, reason: str, **extra: Any) -> None:
    logger.info("[OPS] guard_skip component=%s reason=%s %s", component, reason, extra or "")
