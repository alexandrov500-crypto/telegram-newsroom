"""In-process counters for Redis transport recovery (ops / reconnects). Thread-safe."""

from __future__ import annotations

import threading
import time
from typing import Any

_lock = threading.RLock()
_transport_op_recoveries = 0
_transport_op_retry_events = 0
_reconnect_cycles = 0
_last_reconnect_started_monotonic: float | None = None
_last_reconnect_duration_sec: float | None = None
_connect_failures = 0


def reset_redis_transport_metrics_for_tests() -> None:
    global _transport_op_recoveries, _transport_op_retry_events, _reconnect_cycles
    global _last_reconnect_started_monotonic, _last_reconnect_duration_sec, _connect_failures
    with _lock:
        _transport_op_recoveries = 0
        _transport_op_retry_events = 0
        _reconnect_cycles = 0
        _last_reconnect_started_monotonic = None
        _last_reconnect_duration_sec = None
        _connect_failures = 0


def record_transport_op_retry_event() -> None:
    global _transport_op_retry_events
    with _lock:
        _transport_op_retry_events += 1


def record_transport_op_recovered() -> None:
    global _transport_op_recoveries
    with _lock:
        _transport_op_recoveries += 1


def begin_reconnect_cycle() -> None:
    global _last_reconnect_started_monotonic
    with _lock:
        _last_reconnect_started_monotonic = time.monotonic()


def end_reconnect_cycle() -> None:
    global _reconnect_cycles, _last_reconnect_duration_sec, _last_reconnect_started_monotonic
    with _lock:
        _reconnect_cycles += 1
        if _last_reconnect_started_monotonic is not None:
            _last_reconnect_duration_sec = round(time.monotonic() - _last_reconnect_started_monotonic, 4)
        _last_reconnect_started_monotonic = None


def record_redis_connect_failure() -> None:
    global _connect_failures
    with _lock:
        _connect_failures += 1


def snapshot() -> dict[str, Any]:
    with _lock:
        return {
            "transport_op_recoveries": int(_transport_op_recoveries),
            "transport_op_retry_events": int(_transport_op_retry_events),
            "reconnect_cycles": int(_reconnect_cycles),
            "last_reconnect_duration_sec": _last_reconnect_duration_sec,
            "connect_failures": int(_connect_failures),
        }
