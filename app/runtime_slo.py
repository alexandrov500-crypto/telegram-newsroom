"""Production SLO thresholds for dependency degradation."""
from __future__ import annotations

import time
from typing import Any

from app.config import Settings
from app.dependency_state import AggregateStatus, DependencyStatus, get_dependency_state
from app.runtime_metrics import inc_degraded_transition
from utils.structured_log import log_event

import logging

logger = logging.getLogger(__name__)

_first_degraded_mono: float | None = None


def _settings_slo(settings: Settings | None) -> tuple[int, float, float]:
    if settings is None:
        return 3, 30.0, 120.0
    try:
        return (
            max(1, int(getattr(settings, "runtime_degraded_after_n_failures", 3))),
            max(1.0, float(getattr(settings, "runtime_unavailable_after_n_minutes", 30))),
            max(10.0, float(getattr(settings, "runtime_recovery_stability_window_sec", 120))),
        )
    except (TypeError, ValueError):
        return 3, 30.0, 120.0


def record_dependency_transition(
    dependency: str,
    *,
    new_status: DependencyStatus,
    reason: str,
    settings: Settings | None = None,
) -> None:
    global _first_degraded_mono
    deps = get_dependency_state()
    degraded_n, unavailable_min, recovery_window = _settings_slo(settings)
    now = time.monotonic()

    if new_status == DependencyStatus.DEGRADED:
        inc_degraded_transition()
        deps.consecutive_failures += 1
        deps.last_degraded_reason = reason[:500]
        if _first_degraded_mono is None:
            _first_degraded_mono = now
        if deps.consecutive_failures >= degraded_n:
            log_event(
                logger,
                "runtime.slo.degraded_threshold",
                dependency=dependency,
                consecutive_failures=deps.consecutive_failures,
                threshold=degraded_n,
                reason=reason[:200],
            )
        if _first_degraded_mono is not None and (now - _first_degraded_mono) >= unavailable_min * 60:
            if dependency == "telegram_api" and deps.telegram_api.status != DependencyStatus.UNAVAILABLE:
                deps.set_dependency(
                    "telegram_api",
                    status=DependencyStatus.UNAVAILABLE,
                    detail=f"SLO unavailable after {unavailable_min}m degraded: {reason[:200]}",
                )
                log_event(
                    logger,
                    "runtime.slo.unavailable_threshold",
                    dependency=dependency,
                    minutes=unavailable_min,
                )
    elif new_status == DependencyStatus.HEALTHY:
        if deps.last_recovery_mono and (now - deps.last_recovery_mono) < recovery_window:
            pass
        deps.last_recovery_mono = now
        deps.last_recovery_at_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if deps.consecutive_failures > 0 or deps.last_degraded_reason:
            log_event(
                logger,
                "runtime.slo.recovered",
                dependency=dependency,
                previous_failures=deps.consecutive_failures,
                stability_window_sec=recovery_window,
            )
        deps.consecutive_failures = 0
        deps.last_degraded_reason = ""
        _first_degraded_mono = None

    from db.runtime_ops_repository import persist_runtime_ops_state_fire_and_forget

    persist_runtime_ops_state_fire_and_forget()


def slo_snapshot() -> dict[str, Any]:
    deps = get_dependency_state()
    return {
        "consecutive_failures": deps.consecutive_failures,
        "last_degraded_reason": deps.last_degraded_reason,
        "last_recovery_at": deps.last_recovery_at_iso,
        "aggregate": deps.aggregate_status().value,
    }
