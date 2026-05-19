from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bot.ops_resilience.backpressure import apply_backpressure
from bot.ops_resilience.dependencies import classify_dependencies
from bot.ops_resilience.degradation import build_degradation_matrix
from bot.ops_resilience.failure_budget import compute_failure_budgets
from bot.ops_resilience.forecast import forecast_operational_pressure
from bot.ops_resilience.guidance import build_recovery_guidance
from bot.ops_resilience.recovery_quality import evaluate_recovery_quality
from bot.ops_resilience.repository import ResilienceRepository
from bot.ops_resilience.state_machine import resolve_posture
from bot.storage.db import default_db_path, init_database

logger = logging.getLogger(__name__)

_last_posture: str | None = None
_last_soft_degraded: bool | None = None


def evaluate_resilience_tick(
    *,
    db_path: Path | None = None,
    pulse: dict[str, Any] | None = None,
    base_url: str = "http://127.0.0.1:8080",
    persist: bool = True,
) -> dict[str, Any]:
    """
    Single resilience evaluation pass: dependencies, budgets, posture, backpressure.
    Fail-open; safe to call from watchdog or background loop.
    """
    path = init_database(db_path or default_db_path())
    repo = ResilienceRepository(path)

    if pulse is None:
        try:
            from bot.ops_observation.collector import collect_observation_pulse

            pulse = collect_observation_pulse(base_url=base_url, db_path=str(path))
        except Exception:
            pulse = {}

    soft_info: dict[str, Any] = {}
    try:
        from bot.observability.runtime_degradation import evaluate_soft_degradation

        soft_info = evaluate_soft_degradation()
        _track_soft_degradation_transition(repo, soft_info)
    except Exception:
        soft_info = {}

    dependencies = classify_dependencies(pulse=pulse, db_path=path)
    events = repo.events_since(hours=168)
    recovery_log = repo.recovery_log_since(hours=168)
    recovery_quality = evaluate_recovery_quality(recovery_log)

    failure_budgets = compute_failure_budgets(
        pulse=pulse,
        events=events,
        recovery_log=recovery_log,
    )

    degradation_actions = build_degradation_matrix(
        dependencies,
        pulse=pulse,
        failure_budgets=failure_budgets,
    )

    posture, reason = resolve_posture(
        dependencies=dependencies,
        failure_budgets=failure_budgets,
        recovery_quality=recovery_quality,
        soft_degraded=bool(soft_info.get("soft_degraded")),
    )

    backpressure = apply_backpressure(degradation_actions, posture=posture)
    forecast = forecast_operational_pressure(pulse=pulse, events=events)
    guidance = build_recovery_guidance(
        posture=posture,
        dependencies=dependencies,
        failure_budgets=failure_budgets,
        forecast=forecast,
        degradation_actions=degradation_actions,
    )

    global _last_posture
    if _last_posture != posture:
        repo.record_event(
            "posture_change",
            subsystem="resilience",
            detail={"from": _last_posture, "to": posture, "reason": reason},
        )
        _last_posture = posture

    snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "posture": posture,
        "posture_reason": reason,
        "dependencies": dependencies,
        "failure_budgets": failure_budgets,
        "recovery_quality": recovery_quality,
        "degradation_matrix": degradation_actions,
        "backpressure": backpressure,
        "guidance": guidance,
        "forecast": forecast,
        "soft_degradation": soft_info,
        "context": backpressure.get("applied"),
    }

    if persist:
        try:
            repo.save_state(
                posture=posture,
                posture_reason=reason,
                dependencies=dependencies,
                budgets=failure_budgets,
                backpressure=backpressure,
                guidance=guidance,
                forecast=forecast,
            )
            day = datetime.now(timezone.utc).date().isoformat()
            repo.save_daily(day, snapshot)
        except Exception:
            logger.debug("event=resilience_persist_failed")

    return snapshot


def _track_soft_degradation_transition(
    repo: ResilienceRepository,
    soft_info: dict[str, Any],
) -> None:
    global _last_soft_degraded
    degraded = bool(soft_info.get("soft_degraded"))
    if _last_soft_degraded is None:
        _last_soft_degraded = degraded
        return
    if degraded == _last_soft_degraded:
        return
    outcome = "success" if not degraded and _last_soft_degraded else "entered"
    if degraded and _last_soft_degraded:
        outcome = "repeated"
    repo.record_recovery(
        subsystem="runtime_soft_degrade",
        outcome=outcome,
        detail=soft_info,
    )
    if soft_info.get("changed"):
        repo.record_event(
            "soft_degradation",
            subsystem="runtime",
            detail=soft_info,
        )
    _last_soft_degraded = degraded
