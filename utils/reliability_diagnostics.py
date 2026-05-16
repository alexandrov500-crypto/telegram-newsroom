"""Opt-in reliability diagnostics (retry traces, lock events, snapshot matrices)."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_lock = threading.RLock()
_retry_traces: list[dict[str, Any]] = []
_lock_events: list[dict[str, Any]] = []
_MAX_TRACE = 256


def reset_reliability_diagnostics_for_tests() -> None:
    with _lock:
        _retry_traces.clear()
        _lock_events.clear()


def record_retry_trace(
    *,
    delivery_id: str,
    attempt: int,
    safe_order: bool,
    phase: str,
    extra: dict[str, Any] | None = None,
) -> None:
    row = {
        "ts": time.time(),
        "delivery_id": delivery_id,
        "attempt": attempt,
        "safe_order": safe_order,
        "phase": phase,
        **(extra or {}),
    }
    with _lock:
        _retry_traces.append(row)
        if len(_retry_traces) > _MAX_TRACE:
            del _retry_traces[: len(_retry_traces) - _MAX_TRACE]
    if safe_order:
        from utils.metrics import inc

        inc("worker_retry_safe_reorders", 1)


def record_lock_event(
    *,
    draft_id: int,
    event: str,
    strict: bool,
    redis_available: bool,
    detail: str = "",
) -> None:
    row = {
        "ts": time.time(),
        "draft_id": draft_id,
        "event": event,
        "strict": strict,
        "redis_available": redis_available,
        "detail": detail,
    }
    with _lock:
        _lock_events.append(row)
        if len(_lock_events) > _MAX_TRACE:
            del _lock_events[: len(_lock_events) - _MAX_TRACE]
    from utils.metrics import inc

    if event == "contention":
        inc("publish_lock_contention", 1)
    elif event == "strict_denied":
        inc("publish_lock_strict_denied", 1)
    elif event == "redis_fallback":
        inc("publish_lock_redis_fallback", 1)
    elif event == "stale_suspected":
        inc("publish_lock_stale_suspected", 1)


def retry_traces_snapshot() -> list[dict[str, Any]]:
    with _lock:
        return list(_retry_traces)


def lock_events_snapshot() -> list[dict[str, Any]]:
    with _lock:
        return list(_lock_events)


def lock_recovery_recommendation(events: list[dict[str, Any]] | None = None) -> list[str]:
    ev = events if events is not None else lock_events_snapshot()
    tips: list[str] = []
    if any(e.get("event") == "strict_denied" for e in ev):
        tips.append(
            "Set PUBLISH_LOCK_STRICT=0 only if single-worker; otherwise fix Redis connectivity."
        )
    if any(e.get("event") == "redis_fallback" for e in ev):
        tips.append("Redis fallback active: do not run multiple publishers until Redis is healthy.")
    if any(e.get("event") == "contention" for e in ev):
        tips.append(
            "Lock contention: verify duplicate publish attempts; check draft idempotency keys."
        )
    if not tips:
        tips.append("No lock anomalies recorded in diagnostic buffer.")
    return tips


@dataclass
class SnapshotIntegrityRow:
    scenario: str
    expected_verify: str
    expected_index: str
    operator_action: str


SNAPSHOT_INTEGRITY_MATRIX: tuple[SnapshotIntegrityRow, ...] = (
    SnapshotIntegrityRow("complete tree", "OK/WARNING", "OK/WARNING", "none"),
    SnapshotIntegrityRow("missing required json", "FAIL", "FAIL", "make runtime-nightly"),
    SnapshotIntegrityRow(
        "corrupt manifest checksum", "FAIL", "WARNING", "regenerate manifest or nightly"
    ),
    SnapshotIntegrityRow(
        "restore over live tree", "varies", "varies", "stop writers; restore to staging OUTPUT_DIR"
    ),
    SnapshotIntegrityRow(
        "interrupted restore (partial runtime/)", "FAIL", "FAIL", "re-run restore from snapshot"
    ),
    SnapshotIntegrityRow("corrupt zip sidecar", "N/A", "N/A", "use runtime/ only; re-fetch bundle"),
)


@dataclass
class RestoreCompatibilityRow:
    source: str
    restores_db: bool
    restores_inspection: bool
    live_safe: bool
    notes: str


RESTORE_COMPATIBILITY_MATRIX: tuple[RestoreCompatibilityRow, ...] = (
    RestoreCompatibilityRow("backup_cli zip", True, True, False, "Stop app/workers before restore"),
    RestoreCompatibilityRow("runtime_snapshot.sh", False, True, False, "Inspection tree only"),
    RestoreCompatibilityRow(
        "runtime_restore.sh", False, True, False, "Replaces OUTPUT_DIR/runtime"
    ),
    RestoreCompatibilityRow("failure_drills fixtures", False, True, True, "Read-only validation"),
)


def build_stability_evidence(
    *,
    retry_count: int,
    wal_bytes: int,
    trace_count: int,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "retry_traces_sampled": trace_count,
        "retry_policy_invocations": retry_count,
        "sqlite_wal_bytes_observed": wal_bytes,
        "drift_notes": [],
    }


def write_stability_evidence(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
