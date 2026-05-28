"""Watchdog for in-flight pipeline collect — stall visibility and optional timeout."""

from __future__ import annotations

import os
import threading
import time
from typing import Any

from utils.structured_log import log_event

import logging

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_active = False
_started_mono: float | None = None
_tick_id: str = ""
_last_error: str = ""


def _stall_warn_sec() -> float:
    raw = os.getenv("COLLECT_CYCLE_STALL_WARN_SEC", "120").strip()
    try:
        return max(30.0, min(float(raw), 3600.0))
    except ValueError:
        return 120.0


def collect_timeout_sec() -> float:
    """0 disables wall-clock cap."""
    raw = os.getenv("COLLECT_CYCLE_TIMEOUT_SEC", "").strip()
    if not raw:
        if os.getenv("PRE_PRODUCTION_VALIDATION_MODE", "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }:
            return 300.0
        return 0.0
    try:
        return max(0.0, min(float(raw), 7200.0))
    except ValueError:
        return 0.0


def begin_collect(*, tick_id: str = "") -> None:
    global _active, _started_mono, _tick_id, _last_error
    with _lock:
        _active = True
        _started_mono = time.monotonic()
        _tick_id = tick_id or ""
        _last_error = ""
    log_event(logger, "collect_cycle.started", tick_id=_tick_id)


def end_collect(*, success: bool, error: str = "") -> None:
    global _active, _started_mono, _tick_id, _last_error
    elapsed: float | None = None
    with _lock:
        if _started_mono is not None:
            elapsed = time.monotonic() - _started_mono
        _active = False
        _started_mono = None
        _last_error = error[:300] if error else ""
        tid = _tick_id
        _tick_id = ""
    log_event(
        logger,
        "collect_cycle.finished",
        tick_id=tid,
        success=success,
        elapsed_sec=round(elapsed, 2) if elapsed is not None else None,
        error=_last_error or None,
    )


def check_stall() -> bool:
    """Log warning if collect exceeds stall threshold. Returns True if stalled."""
    with _lock:
        if not _active or _started_mono is None:
            return False
        elapsed = time.monotonic() - _started_mono
        tick = _tick_id
    threshold = _stall_warn_sec()
    if elapsed < threshold:
        return False
    log_event(
        logger,
        "COLLECT_CYCLE_STALLED",
        tick_id=tick,
        elapsed_sec=round(elapsed, 2),
        stall_warn_sec=threshold,
        hint="Telegram DC may be unreachable; check VPN and logs",
    )
    return True


def snapshot() -> dict[str, Any]:
    with _lock:
        if not _active or _started_mono is None:
            return {
                "collect_in_progress": False,
                "collect_elapsed_sec": None,
                "collect_tick_id": None,
                "collect_stalled": False,
                "collect_last_error": _last_error or None,
            }
        elapsed = time.monotonic() - _started_mono
        stalled = elapsed >= _stall_warn_sec()
        return {
            "collect_in_progress": True,
            "collect_elapsed_sec": round(elapsed, 2),
            "collect_tick_id": _tick_id or None,
            "collect_stalled": stalled,
            "collect_last_error": _last_error or None,
        }


def reset_collect_cycle_guard_for_tests() -> None:
    global _active, _started_mono, _tick_id, _last_error
    with _lock:
        _active = False
        _started_mono = None
        _tick_id = ""
        _last_error = ""
