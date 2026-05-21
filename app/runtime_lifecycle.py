"""Structured runtime lifecycle events (JSON logs, runtime_id correlation)."""

from __future__ import annotations

import logging
import time
from typing import Any

from app.build_provenance import load_build_provenance
from app.runtime_notifications import PROCESS_RUNTIME_UUID
from utils.structured_log import log_event

logger = logging.getLogger(__name__)

_BOOT_MONO = time.monotonic()


def reset_runtime_lifecycle_for_tests() -> None:
    global _BOOT_MONO
    _BOOT_MONO = time.monotonic()


def runtime_id() -> str:
    return PROCESS_RUNTIME_UUID


def uptime_sec() -> float:
    return max(0.0, time.monotonic() - _BOOT_MONO)


def _provenance_fields() -> dict[str, str]:
    prov = load_build_provenance()
    return {
        "runtime_id": runtime_id(),
        "git_sha": prov.git_sha,
        "build_version": prov.build_version,
        "build_branch": prov.build_branch,
    }


def emit_lifecycle(
    event: str,
    *,
    event_duration_ms: float | None = None,
    **fields: Any,
) -> None:
    """Emit a lifecycle event (message = event name) with standard correlation fields."""
    payload: dict[str, Any] = {
        **_provenance_fields(),
        "uptime_sec": round(uptime_sec(), 3),
    }
    if event_duration_ms is not None:
        payload["event_duration_ms"] = round(max(0.0, event_duration_ms), 2)
    payload.update(fields)
    log_event(logger, event, **payload)


def lifecycle_span_ms(start_perf: float) -> float:
    return max(0.0, (time.perf_counter() - start_perf) * 1000.0)
