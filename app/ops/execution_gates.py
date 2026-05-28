"""Single source of truth for scheduler/publish gate decisions (precedence-ordered)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.operational_mode import OperationalMode, load_operational_mode, scheduler_allowed


@dataclass(frozen=True)
class GateDecision:
    allowed: bool
    reason: str
    layer: str


def _trace_publish_gate(decision: GateDecision) -> GateDecision:
    try:
        from app.observability.execution_graph_trace import record_publish_gate

        record_publish_gate(allowed=decision.allowed, layer=decision.layer)
    except Exception:
        pass
    return decision


def evaluate_publish_gate(settings: Any, *, trace: bool = True) -> GateDecision:
    """
    Publish gate precedence (first match wins):
    1. GLOBAL_PUBLISH_PAUSE (env)
    2. execution_graph corrupted tick (CRITICAL anomaly safe recovery)
    3. runtime_control PAUSED (env RUNTIME_CONTROL_MODE or persisted)
    4. operational_mode blocked (MAINTENANCE, RECOVERY, READ_ONLY, BOOTSTRAP)
    5. auto_maintenance publish_halted
    """
    try:
        from app.ops.launch_control import enforce_launch_safety

        ls = enforce_launch_safety()
        if not ls.get("valid", True):
            d = GateDecision(False, "launch_control_invalid_state", "launch_control")
            return _trace_publish_gate(d) if trace else d
    except Exception:
        pass

    try:
        from app.observability.execution_graph_safety import is_tick_corrupted
        from utils.operational_context import current_tick_id

        tid = current_tick_id()
        if tid and is_tick_corrupted(tid, settings.runtime_state_dir):
            d = GateDecision(False, "execution_graph_corrupted_tick", "execution_graph_safety")
            return _trace_publish_gate(d) if trace else d
    except Exception:
        pass

    try:
        from app.observability.runtime_protection import autonomous_publish_blocked

        if autonomous_publish_blocked(settings.runtime_state_dir):
            d = GateDecision(False, "runtime_protection_critical", "runtime_protection")
            return _trace_publish_gate(d) if trace else d
    except Exception:
        pass

    try:
        from app.ops.public_incident_safety import incident_frozen

        if incident_frozen(settings.runtime_state_dir):
            d = GateDecision(False, "public_incident_frozen", "public_incident_safety")
            return _trace_publish_gate(d) if trace else d
    except Exception:
        pass

    try:
        from app.ops.live_rollback import rollback_active

        if rollback_active(settings.runtime_state_dir):
            d = GateDecision(False, "live_rollback_active", "live_rollback")
            return _trace_publish_gate(d) if trace else d
    except Exception:
        pass

    try:
        from app.ops.controlled_rollout import evaluate_rollout_publish_gate

        allowed, reason = evaluate_rollout_publish_gate(settings.runtime_state_dir)
        if not allowed:
            d = GateDecision(False, reason, "controlled_rollout")
            return _trace_publish_gate(d) if trace else d
    except Exception:
        pass

    if getattr(settings, "global_publish_pause", False):
        return _trace_publish_gate(GateDecision(False, "global_publish_pause", "env")) if trace else GateDecision(
            False, "global_publish_pause", "env"
        )

    runtime_dir = settings.runtime_state_dir
    try:
        from app.ops.runtime_control import load_runtime_control, RuntimeControlMode

        if load_runtime_control(runtime_dir) == RuntimeControlMode.PAUSED:
            d = GateDecision(False, "runtime_control_paused", "runtime_control")
            return _trace_publish_gate(d) if trace else d
    except Exception:
        pass

    mode = load_operational_mode(runtime_dir, settings)
    if mode in {
        OperationalMode.MAINTENANCE,
        OperationalMode.RECOVERY,
        OperationalMode.READ_ONLY,
        OperationalMode.BOOTSTRAP,
    }:
        d = GateDecision(False, f"operational_mode={mode.value}", "operational_mode")
        return _trace_publish_gate(d) if trace else d

    try:
        from app.reliability.auto_maintenance import publish_halted

        if publish_halted(runtime_dir):
            d = GateDecision(False, "auto_maintenance_halt", "auto_maintenance")
            return _trace_publish_gate(d) if trace else d
    except Exception:
        pass

    d = GateDecision(True, "allowed", "ok")
    return _trace_publish_gate(d) if trace else d


def publish_allowed_unified(settings: Any) -> bool:
    return evaluate_publish_gate(settings).allowed


def evaluate_scheduler_gate(settings: Any) -> GateDecision:
    """Scheduler: operational_mode only (runtime_control does not block ticks)."""
    mode = load_operational_mode(settings.runtime_state_dir, settings)
    if not scheduler_allowed(mode):
        return GateDecision(False, f"operational_mode={mode.value}", "operational_mode")
    return GateDecision(True, "allowed", "ok")
