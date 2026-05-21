"""Degradation/recovery duration tracking (histograms + lifecycle events)."""

from __future__ import annotations

import threading
import time

from utils.metrics import observe_histogram

_lock = threading.Lock()
_degraded_since_mono: float | None = None
_last_state: str = "closed"


def reset_recovery_telemetry_for_tests() -> None:
    global _degraded_since_mono, _last_state
    with _lock:
        _degraded_since_mono = None
        _last_state = "closed"


def note_circuit_state(prev: str, new: str) -> None:
    global _degraded_since_mono, _last_state
    now = time.monotonic()
    with _lock:
        if new in {"open", "half_open"} and _degraded_since_mono is None:
            _degraded_since_mono = now
        if new == "closed" and _degraded_since_mono is not None:
            observe_histogram("recovery_duration_seconds", now - _degraded_since_mono)
            _degraded_since_mono = None
        if prev != "open" and new == "open":
            pass
        if prev == "closed" and new == "open":
            _degraded_since_mono = now
        _last_state = new


def note_degradation_started() -> None:
    global _degraded_since_mono
    with _lock:
        if _degraded_since_mono is None:
            _degraded_since_mono = time.monotonic()


def note_full_recovery() -> None:
    global _degraded_since_mono
    now = time.monotonic()
    with _lock:
        if _degraded_since_mono is not None:
            observe_histogram("recovery_duration_seconds", now - _degraded_since_mono)
            observe_histogram(
                "degradation_duration_seconds",
                now - _degraded_since_mono,
            )
            _degraded_since_mono = None
