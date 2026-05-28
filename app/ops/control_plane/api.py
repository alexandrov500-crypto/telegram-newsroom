"""In-process OPS control plane API (thread/async safe)."""

from __future__ import annotations

from typing import Any

from app.observability.ops_logger import log_ops_change
from app.ops.control_plane.state import OpsState, get_ops_store


def _apply(field: str, value: Any, *, reason: str) -> OpsState:
    st = get_ops_store().patch(**{field: value})
    log_ops_change(field, value, reason=reason)
    return st


def enable_ingestion(*, reason: str = "manual_override") -> OpsState:
    return _apply("ingestion_enabled", True, reason=reason)


def disable_ingestion(*, reason: str = "manual_override") -> OpsState:
    return _apply("ingestion_enabled", False, reason=reason)


def enable_fast_lane(*, reason: str = "manual_override") -> OpsState:
    return _apply("fast_lane_enabled", True, reason=reason)


def disable_fast_lane(*, reason: str = "manual_override") -> OpsState:
    return _apply("fast_lane_enabled", False, reason=reason)


def set_slow_mode(enabled: bool, *, reason: str = "manual_override") -> OpsState:
    return _apply("slow_mode", bool(enabled), reason=reason)


def set_fast_lane_only(enabled: bool, *, reason: str = "manual_override") -> OpsState:
    return _apply("fast_lane_only", bool(enabled), reason=reason)


def set_max_queue_depth(depth: int, *, reason: str = "manual_override") -> OpsState:
    return _apply("max_queue_depth", max(8, int(depth)), reason=reason)


def set_publish_rate_limit(per_min: int, *, reason: str = "manual_override") -> OpsState:
    return _apply("publish_rate_limit_per_min", max(1, int(per_min)), reason=reason)


def emergency_halt(*, reason: str = "system_protection") -> OpsState:
    st = get_ops_store().patch(emergency_halt=True, ingestion_enabled=False)
    log_ops_change("emergency_halt", True, reason=reason)
    log_ops_change("ingestion_enabled", False, reason=f"halt_cascade:{reason}")
    return st


def clear_emergency_halt(*, reason: str = "operator_clear") -> OpsState:
    st = get_ops_store().patch(emergency_halt=False)
    log_ops_change("emergency_halt", False, reason=reason)
    return st


def resume_normal_ops(*, reason: str = "operator_resume") -> OpsState:
    """Restore default operational flags after incident (does not force fast lane env)."""
    st = get_ops_store().patch(
        emergency_halt=False,
        ingestion_enabled=True,
        slow_mode=False,
        fast_lane_only=False,
    )
    for field, val in (
        ("emergency_halt", False),
        ("ingestion_enabled", True),
        ("slow_mode", False),
        ("fast_lane_only", False),
    ):
        log_ops_change(field, val, reason=reason)
    return st


def ops_control_snapshot() -> dict[str, Any]:
    st = get_ops_store().snapshot()
    return {
        **st.to_dict(),
        "publishes_last_minute": get_ops_store().publishes_in_last_minute(),
        "publish_rate_limited": get_ops_store().publish_rate_limited(),
    }
