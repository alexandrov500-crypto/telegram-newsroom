from __future__ import annotations

import itertools
import os
import threading
import time
from contextvars import ContextVar, Token
from typing import Any

_correlation_id: ContextVar[str | None] = ContextVar("newsroom_correlation_id", default=None)
_tick_id: ContextVar[str | None] = ContextVar("newsroom_tick_id", default=None)

_tick_seq = itertools.count(1)
_lock = threading.Lock()


def _deterministic_ids() -> bool:
    return os.getenv("NEWSROOM_LOG_DETERMINISTIC_IDS", "").strip().lower() in {"1", "true", "yes"}


def reset_operational_context_for_tests() -> None:
    """Reset tick sequence (pytest). ContextVar stacks are task-local; seq is global."""
    global _tick_seq
    with _lock:
        _tick_seq = itertools.count(1)


def set_correlation_id(value: str | None) -> Token[str | None]:
    return _correlation_id.set(value)


def reset_correlation_id(token: Token[str | None]) -> None:
    _correlation_id.reset(token)


def set_tick_id(value: str | None) -> Token[str | None]:
    return _tick_id.set(value)


def reset_tick_id(token: Token[str | None]) -> None:
    _tick_id.reset(token)


def begin_pipeline_tick() -> tuple[str, Token[str | None]]:
    """Assign a tick id for this pipeline run; caller must reset_tick_id(token) in finally."""
    with _lock:
        n = next(_tick_seq)
    if _deterministic_ids():
        tid = f"tick-{n:06d}"
    else:
        tid = f"tick-{n}-{time.monotonic_ns()}"
    tok = _tick_id.set(tid)
    return tid, tok


def get_operational_log_fields() -> dict[str, Any]:
    """Fields merged into structured logs (explicit log_event kwargs override these)."""
    out: dict[str, Any] = {}
    c = _correlation_id.get()
    if c:
        out["correlation_id"] = c
    t = _tick_id.get()
    if t:
        out["tick_id"] = t
    return out
