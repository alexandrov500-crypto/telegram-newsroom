"""In-process worker runtime counters (merged into heartbeat / snapshots)."""

from __future__ import annotations

import asyncio
import time
from collections import deque
from typing import Any

_lock = asyncio.Lock()
_started_monotonic = time.monotonic()
_active_jobs = 0
_current_job_type: str | None = None
_last_success_monotonic: float | None = None
_retry_total = 0
_panic_total = 0
_retry_events: deque[float] = deque(maxlen=512)
_active_job_started: dict[str, float] = {}


def reset_worker_runtime_state_for_tests() -> None:
    global _started_monotonic, _active_jobs, _current_job_type, _last_success_monotonic, _retry_total, _panic_total
    global _retry_events, _active_job_started
    _started_monotonic = time.monotonic()
    _active_jobs = 0
    _current_job_type = None
    _last_success_monotonic = None
    _retry_total = 0
    _panic_total = 0
    _retry_events.clear()
    _active_job_started.clear()


async def on_job_start(job_type: str, *, delivery_id: str | None = None) -> None:
    global _active_jobs, _current_job_type
    async with _lock:
        _active_jobs += 1
        _current_job_type = job_type
        if delivery_id:
            _active_job_started[delivery_id] = time.monotonic()


async def on_job_finish(*, success: bool, job_type: str | None = None, delivery_id: str | None = None) -> None:
    global _active_jobs, _current_job_type, _last_success_monotonic
    async with _lock:
        _active_jobs = max(0, _active_jobs - 1)
        if delivery_id:
            _active_job_started.pop(delivery_id, None)
        if success:
            _last_success_monotonic = time.monotonic()
        if _active_jobs == 0:
            _current_job_type = None


async def on_retry() -> None:
    global _retry_total
    async with _lock:
        _retry_total += 1
        _retry_events.append(time.monotonic())


async def on_panic() -> None:
    global _panic_total
    async with _lock:
        _panic_total += 1


def runtime_counters_snapshot() -> dict[str, Any]:
    return {
        "uptime_sec": round(time.monotonic() - _started_monotonic, 3),
        "active_jobs": _active_jobs,
        "current_job_type": _current_job_type,
        "last_success_age_sec": None
        if _last_success_monotonic is None
        else round(time.monotonic() - _last_success_monotonic, 3),
        "retry_total": _retry_total,
        "panic_total": _panic_total,
    }


async def collect_runtime_diag(settings: Any) -> dict[str, Any]:
    window = float(getattr(settings, "runtime_retry_storm_window_sec", 60))
    async with _lock:
        now = time.monotonic()
        burst = sum(1 for t in _retry_events if now - t <= window)
        oldest_active: float | None = None
        if _active_job_started:
            oldest_active = round(now - min(_active_job_started.values()), 3)
        return {
            "retry_burst_window": burst,
            "oldest_active_job_age_sec": oldest_active,
        }
