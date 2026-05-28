"""OPS control plane — runtime-controllable news ingestion."""

from app.ops.control_plane.api import (
    clear_emergency_halt,
    disable_fast_lane,
    disable_ingestion,
    emergency_halt,
    enable_fast_lane,
    enable_ingestion,
    ops_control_snapshot,
    resume_normal_ops,
    set_fast_lane_only,
    set_max_queue_depth,
    set_publish_rate_limit,
    set_slow_mode,
)
from app.ops.control_plane.auto_controller import auto_controller_enabled, evaluate_auto_ops
from app.ops.control_plane.guards import (
    effective_pipeline_interval_minutes,
    emergency_halt_active,
    fast_lane_allowed,
    ingestion_allowed,
    pipeline_tick_allowed,
    publish_allowed_now,
    should_drop_message,
    standard_lane_allowed,
)
from app.ops.control_plane.state import OpsState, get_ops_state, init_ops_state_store

__all__ = [
    "OpsState",
    "auto_controller_enabled",
    "clear_emergency_halt",
    "disable_fast_lane",
    "disable_ingestion",
    "effective_pipeline_interval_minutes",
    "emergency_halt",
    "emergency_halt_active",
    "enable_fast_lane",
    "enable_ingestion",
    "evaluate_auto_ops",
    "fast_lane_allowed",
    "get_ops_state",
    "ingestion_allowed",
    "init_ops_state_store",
    "ops_control_snapshot",
    "pipeline_tick_allowed",
    "publish_allowed_now",
    "resume_normal_ops",
    "set_fast_lane_only",
    "set_max_queue_depth",
    "set_publish_rate_limit",
    "set_slow_mode",
    "should_drop_message",
    "standard_lane_allowed",
]
