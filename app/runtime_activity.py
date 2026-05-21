"""In-process activity timestamps for /health and watchdog (no secrets)."""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

_lock = threading.Lock()
_last_collect_mono: float | None = None
_last_collect_iso: str | None = None
_last_ai_mono: float | None = None
_last_ai_iso: str | None = None
_last_scheduler_tick_mono: float | None = None
_exception_times: deque[float] = deque(maxlen=200)


def _iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def reset_runtime_activity_for_tests() -> None:
    global _last_collect_mono, _last_collect_iso, _last_ai_mono, _last_ai_iso
    global _last_scheduler_tick_mono
    with _lock:
        _last_collect_mono = None
        _last_collect_iso = None
        _last_ai_mono = None
        _last_ai_iso = None
        _last_scheduler_tick_mono = None
        _exception_times.clear()


def record_collect_success(*, new_rows: int) -> None:
    if new_rows <= 0:
        return
    global _last_collect_mono, _last_collect_iso
    now = time.monotonic()
    with _lock:
        _last_collect_mono = now
        _last_collect_iso = _iso_now()


def record_ai_success() -> None:
    global _last_ai_mono, _last_ai_iso
    now = time.monotonic()
    with _lock:
        _last_ai_mono = now
        _last_ai_iso = _iso_now()


def record_scheduler_tick() -> None:
    global _last_scheduler_tick_mono
    with _lock:
        _last_scheduler_tick_mono = time.monotonic()


def record_pipeline_exception() -> None:
    with _lock:
        _exception_times.append(time.monotonic())


def exception_count_in_window(window_sec: float) -> int:
    cutoff = time.monotonic() - max(1.0, window_sec)
    with _lock:
        return sum(1 for t in _exception_times if t >= cutoff)


def seconds_since_collect() -> float | None:
    with _lock:
        if _last_collect_mono is None:
            return None
        return time.monotonic() - _last_collect_mono


def seconds_since_ai() -> float | None:
    with _lock:
        if _last_ai_mono is None:
            return None
        return time.monotonic() - _last_ai_mono


def seconds_since_scheduler_tick() -> float | None:
    with _lock:
        if _last_scheduler_tick_mono is None:
            return None
        return time.monotonic() - _last_scheduler_tick_mono


def activity_snapshot() -> dict[str, Any]:
    with _lock:
        return {
            "last_successful_collect_at": _last_collect_iso,
            "last_successful_ai_at": _last_ai_iso,
            "last_scheduler_tick_mono": _last_scheduler_tick_mono,
        }
