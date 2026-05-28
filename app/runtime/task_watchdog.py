"""Orphan / hung task detection for orchestrated asyncio work."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Any

from app.runtime.task_orchestrator import TaskRecord, active_tasks
from utils.structured_log import log_event

logger = logging.getLogger(__name__)

_DEFAULT_THRESHOLDS: dict[str, float] = {
    "summarize": 300.0,
    "publish": 120.0,
    "collect": 180.0,
    "default": 600.0,
}

_watchdog_task: asyncio.Task[None] | None = None
_hung_count: int = 0


def _threshold_sec(task_type: str, task_name: str) -> float:
    key = task_type if task_type in _DEFAULT_THRESHOLDS else "default"
    if key == "default":
        for part, sec in _DEFAULT_THRESHOLDS.items():
            if part != "default" and part in task_name:
                return sec
    env_key = f"TASK_WATCHDOG_{task_type.upper()}_SEC"
    raw = os.getenv(env_key, "").strip()
    if raw:
        try:
            return max(30.0, float(raw))
        except ValueError:
            pass
    return _DEFAULT_THRESHOLDS.get(key, _DEFAULT_THRESHOLDS["default"])


def _force_cancel_publish() -> bool:
    return os.getenv("TASK_WATCHDOG_FORCE_CANCEL_PUBLISH", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def hung_task_count() -> int:
    return _hung_count


def _scan_once() -> int:
    global _hung_count
    hung = 0
    now = time.monotonic()
    for rec in active_tasks():
        if rec.execution_state != "running":
            continue
        age = now - rec.started_at
        limit = _threshold_sec(rec.task_type, rec.task_name)
        if age < limit:
            continue
        hung += 1
        log_event(
            logger,
            "TASK_TIMEOUT_WARNING",
            task_id=rec.task_id,
            task_name=rec.task_name,
            task_type=rec.task_type,
            trace_id=rec.trace_id,
            age_sec=round(age, 2),
            threshold_sec=limit,
            owner=rec.owner,
        )
        if (
            _force_cancel_publish()
            and "publish" in rec.task_type
            and rec.asyncio_task
            and not rec.asyncio_task.done()
        ):
            rec.metadata["cancel_reason"] = "watchdog_force_cancel"
            rec.asyncio_task.cancel()
            log_event(
                logger,
                "TASK_FORCE_CANCEL",
                task_id=rec.task_id,
                task_name=rec.task_name,
                trace_id=rec.trace_id,
            )
    _hung_count = hung
    return hung


async def _watchdog_loop(interval_sec: float) -> None:
    from app.runtime.task_orchestrator import record_loop_tick

    while True:
        await asyncio.sleep(interval_sec)
        record_loop_tick()
        _scan_once()


def start_task_watchdog(*, interval_sec: float = 30.0) -> asyncio.Task[None] | None:
    global _watchdog_task
    if _watchdog_task and not _watchdog_task.done():
        return _watchdog_task
    from app.runtime.task_orchestrator import create_traced_task

    _watchdog_task = create_traced_task(
        "task_watchdog",
        _watchdog_loop(interval_sec),
        trace_id="watchdog",
        owner="runtime",
        metadata={"task_type": "watchdog", "dedupe_key": "watchdog:main"},
    )
    return _watchdog_task


async def stop_task_watchdog() -> None:
    global _watchdog_task
    if _watchdog_task is None:
        return
    _watchdog_task.cancel()
    try:
        await _watchdog_task
    except asyncio.CancelledError:
        pass
    _watchdog_task = None


def reset_task_watchdog_for_tests() -> None:
    global _watchdog_task, _hung_count
    _watchdog_task = None
    _hung_count = 0
