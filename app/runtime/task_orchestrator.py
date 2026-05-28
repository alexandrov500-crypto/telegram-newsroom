"""
Central asyncio task orchestration — the only module that may call asyncio.create_task.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from collections.abc import Coroutine
from dataclasses import dataclass, field
from typing import Any, TypeVar

from utils.structured_log import log_event

logger = logging.getLogger(__name__)

T = TypeVar("T")

_runtime_generation_id: str = ""
_active_by_id: dict[str, TaskRecord] = {}
_dedupe_index: dict[str, str] = {}
_loop_lag_ms: float = 0.0
_last_loop_tick: float = 0.0


def _env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def strict_trace_mode() -> bool:
    return _env_bool("ASYNC_RUNTIME_STRICT_TRACE", "false")


def duplicate_raises() -> bool:
    return _env_bool("ASYNC_RUNTIME_DUPLICATE_RAISE", "false")


def get_runtime_generation_id() -> str:
    global _runtime_generation_id
    if not _runtime_generation_id:
        _runtime_generation_id = str(uuid.uuid4())
    return _runtime_generation_id


def bump_runtime_generation() -> str:
    global _runtime_generation_id
    _runtime_generation_id = str(uuid.uuid4())
    log_event(
        logger,
        "runtime.generation_bumped",
        generation_id=_runtime_generation_id,
    )
    return _runtime_generation_id


@dataclass(slots=True)
class TaskRecord:
    task_id: str
    task_name: str
    owner: str
    task_type: str
    trace_id: str
    started_at: float
    restart_generation: str
    execution_state: str
    metadata: dict[str, Any] = field(default_factory=dict)
    dedupe_key: str | None = None
    asyncio_task: asyncio.Task[Any] | None = None


def _resolve_trace_id(trace_id: str | None) -> str | None:
    if trace_id and str(trace_id).strip():
        return str(trace_id).strip()
    try:
        from app.state.pipeline_execution_wrapper import current_trace_id

        ctx_trace = current_trace_id()
        if ctx_trace and str(ctx_trace).strip():
            return str(ctx_trace).strip()
    except Exception:
        pass
    return None


def _build_trace_metadata(
    trace_id: str,
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    md = dict(metadata or {})
    md.setdefault("pipeline_trace_id", trace_id)
    md.setdefault("execution_trace_id", trace_id)
    if "parent_trace" not in md:
        md["parent_trace"] = md.get("parent_trace_id") or ""
    if "originating_decision_trace" not in md:
        md["originating_decision_trace"] = md.get("decision_trace_id") or trace_id
    return md


def _dedupe_key(task_name: str, metadata: dict[str, Any]) -> str | None:
    explicit = metadata.get("dedupe_key")
    if explicit:
        return str(explicit)
    draft_id = metadata.get("draft_id")
    task_type = str(metadata.get("task_type") or task_name or "")
    if draft_id is not None and ("publish" in task_type or "publish" in task_name):
        return f"draft_id:{draft_id}"
    phase = metadata.get("phase")
    if phase in ("collect", "summarize", "publish"):
        return f"phase:{phase}"
    if metadata.get("scheduler_loop") or task_name == "scheduler_loop":
        return "scheduler_loop"
    retry_id = metadata.get("retry_id")
    if retry_id is not None:
        return f"retry:{retry_id}"
    return None


def _log_registry(phase: str, record: TaskRecord, **extra: Any) -> None:
    log_event(
        logger,
        "TASK_REGISTRY_TRACE",
        phase=phase,
        task_id=record.task_id,
        task_name=record.task_name,
        owner=record.owner,
        task_type=record.task_type,
        trace_id=record.trace_id,
        execution_state=record.execution_state,
        restart_generation=record.restart_generation,
        dedupe_key=record.dedupe_key,
        started_at=record.started_at,
        extra={**record.metadata, **extra},
    )


def _release_dedupe(record: TaskRecord) -> None:
    if record.dedupe_key and _dedupe_index.get(record.dedupe_key) == record.task_id:
        _dedupe_index.pop(record.dedupe_key, None)


def _mark_complete(record: TaskRecord, state: str) -> None:
    record.execution_state = state
    _log_registry("complete", record)
    _release_dedupe(record)
    _active_by_id.pop(record.task_id, None)


def _wrap_coroutine(
    record: TaskRecord,
    coro: Coroutine[Any, Any, T],
) -> Coroutine[Any, Any, T | None]:
    async def _runner() -> T | None:
        gen_at_start = record.restart_generation
        if gen_at_start != get_runtime_generation_id():
            log_event(
                logger,
                "TASK_STALE_GENERATION_ABORT",
                task_id=record.task_id,
                task_name=record.task_name,
                trace_id=record.trace_id,
                task_generation=gen_at_start,
                current_generation=get_runtime_generation_id(),
            )
            _mark_complete(record, "stale_generation")
            return None
        record.execution_state = "running"
        _log_registry("running", record)
        cancel_reason = str(record.metadata.get("cancel_reason") or "")
        try:
            return await coro
        except asyncio.CancelledError:
            log_event(
                logger,
                "TASK_CANCELLED_TRACE",
                task_id=record.task_id,
                task_name=record.task_name,
                trace_id=record.trace_id,
                owner=record.owner,
                reason=cancel_reason or "cancelled",
                dedupe_key=record.dedupe_key,
            )
            _mark_complete(record, "cancelled")
            raise
        except Exception:
            _mark_complete(record, "failed")
            raise
        else:
            _mark_complete(record, "completed")

    return _runner()


def create_traced_task(
    task_name: str,
    coroutine: Coroutine[Any, Any, T],
    trace_id: str | None,
    owner: str,
    metadata: dict[str, Any] | None = None,
    **kwargs: Any,
) -> asyncio.Task[T | None] | None:
    """
    Schedule traced asyncio work. Returns None when duplicate blocked (default).
    """
    md_in = dict(metadata or {})
    resolved = _resolve_trace_id(trace_id)
    if not resolved:
        if strict_trace_mode():
            log_event(
                logger,
                "TASK_NO_TRACE_BLOCKED",
                task_name=task_name,
                owner=owner,
                strict=True,
            )
            if duplicate_raises():
                raise RuntimeError(f"no trace_id for task {task_name}")
            return None
        resolved = str(uuid.uuid4())
        log_event(
            logger,
            "TASK_TRACE_AUTO_GENERATED",
            task_name=task_name,
            owner=owner,
            trace_id=resolved,
            level=logging.WARNING,
        )
    md = _build_trace_metadata(resolved, md_in)

    dedupe = _dedupe_key(task_name, md)
    if dedupe and dedupe in _dedupe_index:
        existing = _active_by_id.get(_dedupe_index[dedupe])
        if existing and existing.execution_state in ("pending", "running"):
            log_event(
                logger,
                "TASK_DUPLICATE_BLOCKED",
                task_name=task_name,
                owner=owner,
                dedupe_key=dedupe,
                existing_task_id=existing.task_id,
                trace_id=resolved,
            )
            if duplicate_raises():
                raise RuntimeError(f"duplicate task blocked: {dedupe}")
            return None

    task_id = str(uuid.uuid4())
    task_type = str(md.get("task_type") or task_name)
    record = TaskRecord(
        task_id=task_id,
        task_name=task_name,
        owner=owner,
        task_type=task_type,
        trace_id=resolved,
        started_at=time.monotonic(),
        restart_generation=get_runtime_generation_id(),
        execution_state="pending",
        metadata=md,
        dedupe_key=dedupe,
    )
    _active_by_id[task_id] = record
    if dedupe:
        _dedupe_index[dedupe] = task_id

    wrapped = _wrap_coroutine(record, coroutine)
    name = str(kwargs.pop("name", None) or task_name)
    task: asyncio.Task[T | None] = asyncio.create_task(wrapped, name=name, **kwargs)
    record.asyncio_task = task
    _log_registry("register", record)

    def _done_cb(t: asyncio.Task[T | None]) -> None:
        if record.task_id not in _active_by_id:
            return
        if t.cancelled():
            if record.execution_state not in ("cancelled", "stale_generation"):
                log_event(
                    logger,
                    "TASK_CANCELLED_TRACE",
                    task_id=record.task_id,
                    task_name=record.task_name,
                    trace_id=record.trace_id,
                    owner=record.owner,
                    reason=str(record.metadata.get("cancel_reason") or "cancelled"),
                    dedupe_key=record.dedupe_key,
                    via="done_callback",
                )
                _mark_complete(record, "cancelled")
        elif t.exception() is not None and record.execution_state == "running":
            _mark_complete(record, "failed")

    task.add_done_callback(_done_cb)
    return task


def active_tasks() -> list[TaskRecord]:
    return list(_active_by_id.values())


def task_registry_snapshot() -> list[dict[str, Any]]:
    return [
        {
            "task_id": r.task_id,
            "task_name": r.task_name,
            "owner": r.owner,
            "task_type": r.task_type,
            "trace_id": r.trace_id,
            "execution_state": r.execution_state,
            "restart_generation": r.restart_generation,
            "dedupe_key": r.dedupe_key,
            "age_sec": round(time.monotonic() - r.started_at, 2),
        }
        for r in _active_by_id.values()
    ]


def record_loop_tick() -> None:
    """Call periodically to populate event_loop_lag_ms for health."""
    global _loop_lag_ms, _last_loop_tick
    now = time.monotonic()
    if _last_loop_tick > 0:
        drift_ms = max(0.0, (now - _last_loop_tick - 1.0) * 1000.0)
        _loop_lag_ms = max(_loop_lag_ms * 0.9, drift_ms)
    _last_loop_tick = now


def orchestrator_health_snapshot() -> dict[str, Any]:
    hung = 0
    try:
        from app.runtime.task_watchdog import hung_task_count

        hung = hung_task_count()
    except Exception:
        pass
    active = len(_active_by_id)
    all_have_trace = all(bool(r.trace_id) for r in _active_by_id.values()) if active else True
    return {
        "event_loop_lag_ms": round(_loop_lag_ms, 2),
        "active_task_count": active,
        "hung_task_count": hung,
        "scheduler_generation": get_runtime_generation_id(),
        "async_integrity_ok": all_have_trace and active >= 0,
        "strict_trace_mode": strict_trace_mode(),
        "tasks": task_registry_snapshot(),
    }


def reset_task_orchestrator_for_tests() -> None:
    global _runtime_generation_id, _loop_lag_ms, _last_loop_tick
    _runtime_generation_id = ""
    _active_by_id.clear()
    _dedupe_index.clear()
    _loop_lag_ms = 0.0
    _last_loop_tick = 0.0
    bump_runtime_generation()
