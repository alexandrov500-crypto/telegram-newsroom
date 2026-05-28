"""Runtime ownership: single active newsroom process guarantees."""

from app.ops.runtime.active_runtime import clear_active_runtime, register_active_runtime
from app.ops.runtime.pipeline_gate import allow_processing, log_gate_blocked
from app.ops.runtime.singleton_guard import (
    RuntimeSingletonGuard,
    enforce_singleton_or_exit,
    get_singleton_guard,
    release_singleton_guard,
)

__all__ = [
    "RuntimeSingletonGuard",
    "allow_processing",
    "clear_active_runtime",
    "enforce_singleton_or_exit",
    "get_singleton_guard",
    "log_gate_blocked",
    "register_active_runtime",
    "release_singleton_guard",
]
