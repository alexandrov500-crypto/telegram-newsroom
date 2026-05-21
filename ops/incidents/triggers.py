"""Incident trigger evaluation with cooldown (non-blocking)."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Any

from ops.incidents.bundle import write_incident_bundle_sync
from ops.runtime_timeline import record_timeline
from utils.structured_log import log_event

logger = logging.getLogger(__name__)

_cooldown_until: dict[str, float] = {}
_openai_fail_window: list[float] = []
_queue_overflow_window: list[float] = []
_pending_task: asyncio.Task[None] | None = None


def reset_incident_triggers_for_tests() -> None:
    global _pending_task
    _cooldown_until.clear()
    _openai_fail_window.clear()
    _queue_overflow_window.clear()
    if _pending_task and not _pending_task.done():
        _pending_task.cancel()
    _pending_task = None


def _cooldown_sec() -> float:
    return max(60.0, float(os.getenv("INCIDENT_TRIGGER_COOLDOWN_SEC", "900")))


def _in_cooldown(trigger: str) -> bool:
    return time.monotonic() < _cooldown_until.get(trigger, 0.0)


def _arm_cooldown(trigger: str) -> None:
    _cooldown_until[trigger] = time.monotonic() + _cooldown_sec()


def _incidents_dir(settings: Any) -> Path:
    base = Path(str(getattr(settings, "runtime_state_dir", "var/runtime") or "var/runtime"))
    return base / "incidents"


def maybe_trigger_incident(
    settings: Any,
    trigger: str,
    *,
    detail: dict[str, Any] | None = None,
    force: bool = False,
) -> None:
    """Schedule incident bundle if cooldown allows (never blocks caller)."""
    if not force and _in_cooldown(trigger):
        return
    _arm_cooldown(trigger)
    record_timeline("incident.triggered", summary=trigger, trigger=trigger)

    async def _run() -> None:
        try:
            path = await asyncio.to_thread(
                write_incident_bundle_sync,
                incidents_dir=_incidents_dir(settings),
                trigger=trigger,
                detail=detail,
            )
            if path:
                log_event(
                    logger,
                    "incident.bundle.created",
                    trigger=trigger,
                    path=path,
                    subsystem="incidents",
                )
                record_timeline("incident.bundle.created", summary=path, path=path)
        except Exception as exc:
            log_event(
                logger,
                "incident.bundle.failed",
                trigger=trigger,
                error=repr(exc),
                subsystem="incidents",
            )

    global _pending_task
    try:
        loop = asyncio.get_running_loop()
        _pending_task = loop.create_task(_run())
    except RuntimeError:
        write_incident_bundle_sync(
            incidents_dir=_incidents_dir(settings),
            trigger=trigger,
            detail=detail,
        )


def note_openai_failure(settings: Any, *, reason: str = "") -> None:
    now = time.monotonic()
    window = max(60.0, float(os.getenv("INCIDENT_OPENAI_FAIL_WINDOW_SEC", "300")))
    threshold = max(3, int(os.getenv("INCIDENT_OPENAI_FAIL_THRESHOLD", "8")))
    _openai_fail_window[:] = [t for t in _openai_fail_window if now - t <= window]
    _openai_fail_window.append(now)
    record_timeline("ai.failure", summary=reason[:120] or "openai_failure")
    if len(_openai_fail_window) >= threshold:
        maybe_trigger_incident(
            settings,
            "openai_failure_burst",
            detail={"count": len(_openai_fail_window), "window_sec": window, "reason": reason[:200]},
        )


def note_queue_overflow(settings: Any, *, kind: str, depth: int) -> None:
    now = time.monotonic()
    window = max(30.0, float(os.getenv("INCIDENT_QUEUE_OVERFLOW_WINDOW_SEC", "120")))
    threshold = max(2, int(os.getenv("INCIDENT_QUEUE_OVERFLOW_THRESHOLD", "3")))
    _queue_overflow_window[:] = [t for t in _queue_overflow_window if now - t <= window]
    _queue_overflow_window.append(now)
    record_timeline("queue.overflow", summary=kind, depth=depth)
    if len(_queue_overflow_window) >= threshold:
        maybe_trigger_incident(
            settings,
            "queue_overflow_burst",
            detail={"events": len(_queue_overflow_window), "kind": kind, "depth": depth},
        )


def note_watchdog_alert(settings: Any, alert: str, *, fields: dict[str, Any] | None = None) -> None:
    from ops.runtime_timeline import inc_watchdog_alerts

    inc_watchdog_alerts()
    record_timeline(f"watchdog.{alert}", summary=alert, **(fields or {}))
    mapping = {
        "scheduler.stalled": "watchdog_scheduler_stalled",
        "collector.stalled": "watchdog_collector_stalled",
        "exception_burst": "watchdog_exception_burst",
        "event_loop.lag": "watchdog_event_loop_lag",
    }
    trig = mapping.get(alert, f"watchdog_{alert}")
    maybe_trigger_incident(settings, trig, detail=fields)


def note_degradation_transition(settings: Any, *, dependency: str, reason: str) -> None:
    record_timeline("runtime.degraded", summary=dependency, dependency=dependency, reason=reason[:200])
    maybe_trigger_incident(
        settings,
        "runtime_degradation",
        detail={"dependency": dependency, "reason": reason[:300]},
    )
