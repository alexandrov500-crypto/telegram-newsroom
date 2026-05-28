"""Adaptive runtime protection — degradation detection and self-pressure (no process kill)."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Any

from app.observability.runtime_health import collect_health_snapshot, load_health_snapshots, sample_and_persist
from utils.structured_log import log_event

logger = logging.getLogger(__name__)

_lock = threading.RLock()


class RuntimeHealthLevel(str, Enum):
    NORMAL = "normal"
    ELEVATED = "elevated"
    DEGRADED = "degraded"
    CRITICAL = "critical"


_LEVEL_RANK = {
    RuntimeHealthLevel.NORMAL: 0,
    RuntimeHealthLevel.ELEVATED: 1,
    RuntimeHealthLevel.DEGRADED: 2,
    RuntimeHealthLevel.CRITICAL: 3,
}


def _state_path(runtime_dir: str) -> Path:
    return Path(runtime_dir).expanduser().resolve() / "runtime_protection_state.json"


def _default_state() -> dict[str, Any]:
    return {
        "current_state": RuntimeHealthLevel.NORMAL.value,
        "entered_at": None,
        "reasons": [],
        "active_protections": [],
        "recovery_conditions": [],
        "transition_history": [],
        "protection_activation_count": 0,
        "recovery_count": 0,
        "healthy_samples_streak": 0,
        "last_critical_at": None,
    }


def load_protection_state(runtime_dir: str) -> dict[str, Any]:
    path = _state_path(runtime_dir)
    if not path.is_file():
        return _default_state()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else _default_state()
    except (OSError, json.JSONDecodeError):
        return _default_state()


def save_protection_state(runtime_dir: str, state: dict[str, Any]) -> None:
    path = _state_path(runtime_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def classify_degradation(snapshot: dict[str, Any]) -> tuple[RuntimeHealthLevel, list[str]]:
    flags = list(snapshot.get("degradation_flags") or [])
    if not flags:
        return RuntimeHealthLevel.NORMAL, []

    critical_flags = {
        "memory_drift_high",
        "tick_duration_p95_high",
        "exception_burst",
        "event_loop_block",
    }
    degraded_flags = {
        "retry_rate_high",
        "openai_latency_high",
        "publish_latency_high",
        "scheduler_lag_high",
        "queue_backlog_high",
    }

    critical_hits = [f for f in flags if f in critical_flags]
    degraded_hits = [f for f in flags if f in degraded_flags]

    if len(critical_hits) >= 2 or (
        "memory_drift_high" in critical_hits and "tick_duration_p95_high" in critical_hits
    ):
        return RuntimeHealthLevel.CRITICAL, flags
    if critical_hits:
        return RuntimeHealthLevel.DEGRADED, flags
    if len(degraded_hits) >= 2:
        return RuntimeHealthLevel.DEGRADED, flags
    if degraded_hits or flags:
        return RuntimeHealthLevel.ELEVATED, flags
    return RuntimeHealthLevel.NORMAL, []


def _protections_for_level(level: RuntimeHealthLevel) -> list[str]:
    if level == RuntimeHealthLevel.NORMAL:
        return []
    if level == RuntimeHealthLevel.ELEVATED:
        return ["log_elevated_warning"]
    if level == RuntimeHealthLevel.DEGRADED:
        return [
            "slow_scheduler_ticks",
            "reduce_retry_aggressiveness",
            "suppress_nonessential_analytics",
            "limit_summarize_pressure",
        ]
    return [
        "block_autonomous_publish",
        "slow_scheduler_ticks",
        "reduce_retry_aggressiveness",
        "suppress_nonessential_analytics",
        "continue_ingest_and_diagnostics",
    ]


def _recovery_conditions_for(level: RuntimeHealthLevel) -> list[str]:
    if level == RuntimeHealthLevel.NORMAL:
        return []
    need = int(os.getenv("RUNTIME_PROTECTION_RECOVERY_SAMPLES", "5"))
    return [
        f"sustained_normal_snapshots>={need}",
        "no_critical_execution_graph_anomalies",
        "stable_latency_and_memory_trend",
    ]


def _has_critical_execution_graph(runtime_dir: str) -> bool:
    try:
        from app.observability.execution_graph_safety import safety_payload

        sp = safety_payload(runtime_dir)
        return bool(sp.get("safe_recovery_active")) or int(sp.get("corrupted_tick_count") or 0) > 0
    except Exception:
        return False


def _trends_stable(snapshots: list[dict[str, Any]], *, window: int = 5) -> bool:
    if len(snapshots) < window:
        return False
    tail = snapshots[-window:]
    drifts = [float(s.get("rss_drift_mb") or 0) for s in tail]
    p95s = [float(s.get("p95_tick_duration_sec") or 0) for s in tail]
    if not drifts or not p95s:
        return True
    drift_span = max(drifts) - min(drifts)
    p95_span = max(p95s) - min(p95s) if max(p95s) > 0 else 0
    return drift_span < float(os.getenv("RUNTIME_PROTECTION_DRIFT_STABLE_MB", "64")) and p95_span < float(
        os.getenv("RUNTIME_PROTECTION_P95_STABLE_SEC", "120")
    )


def try_automatic_recovery(runtime_dir: str, snapshot: dict[str, Any]) -> bool:
    """Step down one level after sustained health; never skip CRITICAL→NORMAL in one step."""
    state = load_protection_state(runtime_dir)
    current = RuntimeHealthLevel(str(state.get("current_state") or "normal"))
    if current == RuntimeHealthLevel.NORMAL:
        return False

    level, _ = classify_degradation(snapshot)
    if level != RuntimeHealthLevel.NORMAL:
        state["healthy_samples_streak"] = 0
        save_protection_state(runtime_dir, state)
        return False

    if _has_critical_execution_graph(runtime_dir):
        state["healthy_samples_streak"] = 0
        save_protection_state(runtime_dir, state)
        return False

    try:
        from app.ops.public_incident_safety import restart_loop_guard_active

        if restart_loop_guard_active(runtime_dir):
            state["healthy_samples_streak"] = 0
            save_protection_state(runtime_dir, state)
            return False
    except Exception:
        pass

    snapshots = load_health_snapshots(runtime_dir, limit=20)
    if not _trends_stable(snapshots):
        state["healthy_samples_streak"] = 0
        save_protection_state(runtime_dir, state)
        return False

    streak = int(state.get("healthy_samples_streak") or 0) + 1
    need = int(os.getenv("RUNTIME_PROTECTION_RECOVERY_SAMPLES", "5"))
    state["healthy_samples_streak"] = streak
    if streak < need:
        save_protection_state(runtime_dir, state)
        return False

    rank = _LEVEL_RANK[current]
    if rank <= 0:
        return False
    order = [
        RuntimeHealthLevel.NORMAL,
        RuntimeHealthLevel.ELEVATED,
        RuntimeHealthLevel.DEGRADED,
        RuntimeHealthLevel.CRITICAL,
    ]
    new_level = order[rank - 1]
    _transition(runtime_dir, state, new_level, ["automatic_recovery"], recovered=True)
    return True


def _transition(
    runtime_dir: str,
    state: dict[str, Any],
    new_level: RuntimeHealthLevel,
    reasons: list[str],
    *,
    recovered: bool = False,
) -> None:
    prev = RuntimeHealthLevel(str(state.get("current_state") or "normal"))
    if prev == new_level and not recovered:
        state["reasons"] = reasons[:24]
        state["active_protections"] = _protections_for_level(new_level)
        save_protection_state(runtime_dir, state)
        return

    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    hist = state.setdefault("transition_history", [])
    hist.append(
        {
            "from": prev.value,
            "to": new_level.value,
            "at": now,
            "reasons": reasons[:12],
        }
    )
    state["transition_history"] = hist[-200:]

    if _LEVEL_RANK[new_level] > _LEVEL_RANK[prev]:
        state["protection_activation_count"] = int(state.get("protection_activation_count") or 0) + 1
        if new_level == RuntimeHealthLevel.CRITICAL:
            state["last_critical_at"] = now
            log_event(
                logger,
                "runtime_protection_mode_enabled",
                protection_level=new_level.value,
                reasons=reasons[:8],
            )
            try:
                from app.ops.public_incident_safety import on_runtime_critical

                on_runtime_critical(
                    runtime_dir,
                    reasons=reasons[:12],
                    protection_snapshot={
                        "current_state": new_level.value,
                        "entered_at": now,
                        "reasons": reasons[:12],
                    },
                )
            except Exception as exc:
                log_event(logger, "public_incident_safety.hook_failed", error=repr(exc)[:120])
        log_event(
            logger,
            "runtime_state_transition",
            previous=prev.value,
            current=new_level.value,
            reasons=reasons[:8],
        )
    elif recovered or _LEVEL_RANK[new_level] < _LEVEL_RANK[prev]:
        state["recovery_count"] = int(state.get("recovery_count") or 0) + 1
        state["healthy_samples_streak"] = 0
        log_event(
            logger,
            "runtime_recovered",
            previous=prev.value,
            current=new_level.value,
            reasons=reasons[:8],
        )
        log_event(
            logger,
            "runtime_state_transition",
            previous=prev.value,
            current=new_level.value,
            recovery=True,
        )

    state["current_state"] = new_level.value
    state["entered_at"] = now
    state["reasons"] = reasons[:24]
    state["active_protections"] = _protections_for_level(new_level)
    state["recovery_conditions"] = _recovery_conditions_for(new_level)
    save_protection_state(runtime_dir, state)


def evaluate_and_apply_protection(runtime_dir: str, *, settings: Any | None = None) -> dict[str, Any]:
    """Sample health, classify, transition state, attempt recovery."""
    snap = sample_and_persist(runtime_dir, settings=settings)
    level, flags = classify_degradation(snap)
    state = load_protection_state(runtime_dir)
    current = RuntimeHealthLevel(str(state.get("current_state") or "normal"))

    if _LEVEL_RANK[level] > _LEVEL_RANK[current]:
        _transition(runtime_dir, state, level, flags)
    elif level == RuntimeHealthLevel.NORMAL:
        if try_automatic_recovery(runtime_dir, snap):
            state = load_protection_state(runtime_dir)
        elif current == RuntimeHealthLevel.ELEVATED and not flags:
            _transition(runtime_dir, state, RuntimeHealthLevel.NORMAL, ["cleared_elevated"])
        else:
            state["reasons"] = flags
            save_protection_state(runtime_dir, state)
    elif _LEVEL_RANK[level] < _LEVEL_RANK[current]:
        try_automatic_recovery(runtime_dir, snap)
        state = load_protection_state(runtime_dir)
    else:
        state["reasons"] = flags
        state["active_protections"] = _protections_for_level(current)
        save_protection_state(runtime_dir, state)

    if level == RuntimeHealthLevel.ELEVATED:
        log_event(logger, "runtime_health_elevated", flags=flags[:12])

    return {
        "snapshot": snap,
        "classified_level": level.value,
        "state": load_protection_state(runtime_dir),
    }


def current_protection_level(runtime_dir: str | None = None) -> RuntimeHealthLevel:
    import os as _os

    rd = runtime_dir or _os.getenv("RUNTIME_STATE_DIR", "var/runtime")
    return RuntimeHealthLevel(str(load_protection_state(rd).get("current_state") or "normal"))


def active_protections(runtime_dir: str | None = None) -> list[str]:
    import os as _os

    rd = runtime_dir or _os.getenv("RUNTIME_STATE_DIR", "var/runtime")
    return list(load_protection_state(rd).get("active_protections") or [])


def autonomous_publish_blocked(runtime_dir: str | None = None) -> bool:
    return current_protection_level(runtime_dir) == RuntimeHealthLevel.CRITICAL


def pipeline_interval_multiplier(runtime_dir: str | None = None) -> float:
    level = current_protection_level(runtime_dir)
    if level == RuntimeHealthLevel.DEGRADED:
        return float(os.getenv("RUNTIME_PROTECTION_DEGRADED_INTERVAL_MULT", "1.25"))
    if level == RuntimeHealthLevel.CRITICAL:
        return float(os.getenv("RUNTIME_PROTECTION_CRITICAL_INTERVAL_MULT", "1.5"))
    return 1.0


def analytics_suppressed(runtime_dir: str | None = None) -> bool:
    return current_protection_level(runtime_dir) in {
        RuntimeHealthLevel.DEGRADED,
        RuntimeHealthLevel.CRITICAL,
    }


def retry_batch_limit(default: int, runtime_dir: str | None = None) -> int:
    level = current_protection_level(runtime_dir)
    if level in {RuntimeHealthLevel.DEGRADED, RuntimeHealthLevel.CRITICAL}:
        return max(1, default // 2)
    return default


def summarize_pressure_limited(runtime_dir: str | None = None) -> bool:
    return current_protection_level(runtime_dir) in {
        RuntimeHealthLevel.DEGRADED,
        RuntimeHealthLevel.CRITICAL,
    }


def protection_payload(runtime_dir: str) -> dict[str, Any]:
    state = load_protection_state(runtime_dir)
    return {
        "current_state": state.get("current_state") or "UNKNOWN",
        "entered_at": state.get("entered_at") or "UNKNOWN",
        "active_protections": state.get("active_protections") or [],
        "protection_activation_count": state.get("protection_activation_count")
        if state.get("protection_activation_count") is not None
        else "UNKNOWN",
        "recovery_count": state.get("recovery_count") if state.get("recovery_count") is not None else "UNKNOWN",
        "last_critical_at": state.get("last_critical_at") or "UNKNOWN",
    }
