from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

WARN_JOB_SEC = 1.0
CRITICAL_JOB_SEC = 3.0
WARN_DB_SEC = 0.25
CRITICAL_DB_SEC = 1.0


@dataclass
class LoopDiagnosticsState:
    event_loop_lag_max: float = 0.0
    event_loop_lag_avg: float = 0.0
    event_loop_lag_samples: int = 0
    last_lag_sec: float = 0.0
    slow_job_count: int = 0
    slow_db_operation_count: int = 0
    publishing_active: bool = False
    telegram_request_active: bool = False
    openai_request_active: bool = False
    current_db_operation: str | None = None
    current_job: str | None = None
    recent_slow_jobs: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=32))
    recent_jobs: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=64))


_state = LoopDiagnosticsState()
_lag_sum: float = 0.0


def get_loop_diagnostics() -> LoopDiagnosticsState:
    return _state


def record_event_loop_lag(lag_sec: float) -> None:
    global _lag_sum
    s = _state
    s.last_lag_sec = lag_sec
    s.event_loop_lag_samples += 1
    _lag_sum += lag_sec
    s.event_loop_lag_avg = _lag_sum / max(1, s.event_loop_lag_samples)
    s.event_loop_lag_max = max(s.event_loop_lag_max, lag_sec)
    try:
        from bot.observability.metrics import set_event_loop_lag_stats

        set_event_loop_lag_stats(s.event_loop_lag_avg, s.event_loop_lag_max)
    except Exception:
        pass


def _active_task_names() -> list[str]:
    try:
        loop = asyncio.get_running_loop()
        names: list[str] = []
        for task in asyncio.all_tasks(loop):
            if task.done():
                continue
            name = task.get_name() or "task"
            coro = task.get_coro()
            qual = getattr(coro, "__qualname__", None) or getattr(coro, "__name__", "")
            names.append(f"{name}:{qual}" if qual else name)
        return sorted(names)[:40]
    except RuntimeError:
        return []


def _scheduler_job_count() -> int:
    try:
        from utils.scheduler_diagnostics import scheduler_diagnostics_snapshot

        snap = scheduler_diagnostics_snapshot()
        return int(snap.get("run_count", 0))
    except Exception:
        return 0


def collect_lag_context() -> dict[str, Any]:
    s = _state
    return {
        "lag_sec": round(s.last_lag_sec, 4),
        "lag_avg_sec": round(s.event_loop_lag_avg, 4),
        "lag_max_sec": round(s.event_loop_lag_max, 4),
        "active_tasks": _active_task_names(),
        "active_task_count": len(_active_task_names()),
        "scheduler_jobs": _scheduler_job_count(),
        "publishing_active": s.publishing_active,
        "db_operation": s.current_db_operation,
        "current_job": s.current_job,
        "telegram_request_active": s.telegram_request_active,
        "openai_request_active": s.openai_request_active,
        "slow_job_count": s.slow_job_count,
        "slow_db_operation_count": s.slow_db_operation_count,
        "recent_slow_jobs": list(s.recent_slow_jobs)[-5:],
    }


def snapshot() -> dict[str, Any]:
    s = _state
    try:
        from bot.observability.loop_registry import get_loop_registry

        loops = get_loop_registry().snapshot()
    except Exception:
        loops = {}
    out = {
        "event_loop_lag_avg": round(s.event_loop_lag_avg, 4),
        "event_loop_lag_max": round(s.event_loop_lag_max, 4),
        "slow_job_count": s.slow_job_count,
        "slow_db_operation_count": s.slow_db_operation_count,
        "publishing_active": s.publishing_active,
        "current_job": s.current_job,
        "current_db_operation": s.current_db_operation,
        "loops": loops,
        "recent_slow_jobs": list(s.recent_slow_jobs)[-10:],
    }
    try:
        from bot.observability.loop_health import snapshot as loop_health_snapshot
        from bot.runtime.state import runtime_state

        out["loop_health"] = loop_health_snapshot()
        out["soft_degraded"] = runtime_state.soft_degraded
    except Exception:
        pass
    return out


def _record_job(job_name: str, duration_sec: float, *, error: str | None = None) -> None:
    rec = {
        "job_name": job_name,
        "duration_sec": round(duration_sec, 4),
        "error": error,
        "ts": time.time(),
    }
    _state.recent_jobs.append(rec)
    level: str | None = None
    if duration_sec >= CRITICAL_JOB_SEC:
        level = "critical"
        _state.slow_job_count += 1
        _state.recent_slow_jobs.append(rec)
    elif duration_sec >= WARN_JOB_SEC:
        level = "warning"
        _state.slow_job_count += 1
        _state.recent_slow_jobs.append(rec)
    if level:
        logger.warning(
            "event=slow_job job_name=%s duration_sec=%.3f level=%s",
            job_name,
            duration_sec,
            level,
        )
    try:
        from bot.observability.metrics import record_slow_job

        if duration_sec >= WARN_JOB_SEC:
            record_slow_job(job_name, duration_sec)
    except Exception:
        pass


@asynccontextmanager
async def timed_async_job(job_name: str):
    s = _state
    prev = s.current_job
    s.current_job = job_name
    started = time.perf_counter()
    err: str | None = None
    try:
        yield
    except Exception as exc:
        err = type(exc).__name__
        raise
    finally:
        duration = time.perf_counter() - started
        s.current_job = prev
        _record_job(job_name, duration, error=err)


@contextmanager
def track_sync_db(operation: str):
    s = _state
    prev = s.current_db_operation
    s.current_db_operation = operation
    started = time.perf_counter()
    try:
        yield
    finally:
        duration = time.perf_counter() - started
        s.current_db_operation = prev
        if duration >= WARN_DB_SEC:
            s.slow_db_operation_count += 1
            level = "critical" if duration >= CRITICAL_DB_SEC else "warning"
            logger.warning(
                "event=slow_db_operation operation=%s duration_sec=%.3f level=%s",
                operation,
                duration,
                level,
            )
            try:
                from bot.observability.metrics import record_slow_db_operation

                record_slow_db_operation(operation, duration)
            except Exception:
                pass


@contextmanager
def publishing_active():
    s = _state
    s.publishing_active = True
    try:
        yield
    finally:
        s.publishing_active = False


@contextmanager
def telegram_request_active():
    s = _state
    s.telegram_request_active = True
    try:
        yield
    finally:
        s.telegram_request_active = False


@contextmanager
def openai_request_active():
    s = _state
    s.openai_request_active = True
    try:
        yield
    finally:
        s.openai_request_active = False
