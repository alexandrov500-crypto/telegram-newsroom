"""Automatic OPS adjustments from queue depth and pipeline lag."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from app.observability.ops_logger import log_ops_change
from app.ops.control_plane.state import get_ops_state, get_ops_store

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def auto_controller_enabled() -> bool:
    return os.getenv("OPS_AUTO_CONTROLLER", "true").strip().lower() in {"1", "true", "yes", "on"}


def _queue_depths() -> dict[str, int]:
    try:
        from app.ops.queues import get_lane_queues

        reg = get_lane_queues()
        if reg is None:
            return {"fast": 0, "standard": 0, "slow": 0, "total": 0}
        d = reg.depths()
        total = int(d.get("fast", 0)) + int(d.get("standard", 0)) + int(d.get("slow", 0))
        return {"fast": int(d["fast"]), "standard": int(d["standard"]), "slow": int(d["slow"]), "total": total}
    except Exception:
        return {"fast": 0, "standard": 0, "slow": 0, "total": 0}


def _pipeline_lag_sec(settings: Any | None) -> float:
    last = get_ops_store().last_pipeline_tick_unix()
    if last <= 0:
        return 0.0
    base_min = 15
    if settings is not None:
        base_min = max(1, int(getattr(settings, "pipeline_interval_minutes", 15)))
    st = get_ops_state()
    expected = base_min * 60 * (3 if st.slow_mode else 1)
    return max(0.0, time.time() - last - expected)


def evaluate_auto_ops(settings: Any | None = None) -> dict[str, Any]:
    """
    Auto-tune slow_mode / fast_lane_only from queue pressure and lag.
    Never clears emergency_halt (operator-only).
    """
    if not auto_controller_enabled():
        return {"applied": False, "reason": "disabled"}

    st = get_ops_state()
    if st.emergency_halt:
        return {"applied": False, "reason": "emergency_halt"}

    depths = _queue_depths()
    total = depths["total"]
    warn = _env_int("OPS_AUTO_SLOW_DEPTH", 64)
    critical = _env_int("OPS_AUTO_CRITICAL_DEPTH", 128)
    fast_only = _env_int("OPS_AUTO_FAST_ONLY_DEPTH", 96)
    lag_warn = _env_int("OPS_AUTO_LAG_WARN_SEC", 900)

    lag = _pipeline_lag_sec(settings)
    store = get_ops_store()
    changes: list[str] = []

    if total >= critical or lag >= lag_warn * 2:
        if not st.slow_mode:
            store.patch(slow_mode=True)
            log_ops_change("slow_mode", True, reason=f"queue_depth={total}|lag_sec={lag:.0f}")
            changes.append("slow_mode_on")
        if total >= fast_only and not st.fast_lane_only:
            store.patch(fast_lane_only=True)
            log_ops_change("fast_lane_only", True, reason=f"queue_depth={total}")
            changes.append("fast_lane_only_on")
    elif total >= warn:
        if not st.slow_mode:
            store.patch(slow_mode=True)
            log_ops_change("slow_mode", True, reason=f"queue_depth={total}")
            changes.append("slow_mode_on")
    elif total < warn // 2 and lag < lag_warn:
        st2 = get_ops_state()
        if st2.slow_mode or st2.fast_lane_only:
            store.patch(slow_mode=False, fast_lane_only=False)
            log_ops_change("slow_mode", False, reason="system_stable")
            log_ops_change("fast_lane_only", False, reason="system_stable")
            changes.append("restored_normal")

    return {
        "applied": bool(changes),
        "changes": changes,
        "depths": depths,
        "pipeline_lag_sec": round(lag, 1),
        "thresholds": {"warn": warn, "critical": critical, "fast_only": fast_only},
    }
