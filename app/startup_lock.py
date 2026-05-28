"""Process-level startup lock — delegates to RuntimeSingletonGuard (newsroom.lock)."""

from __future__ import annotations

import logging
from typing import Any

from app.ops.runtime.singleton_guard import (
    enforce_singleton_or_exit,
    get_singleton_guard,
    lock_path_for_runtime,
    release_singleton_guard,
)

logger = logging.getLogger(__name__)


def acquire_runtime_startup_lock(settings: Any) -> None:
    """Acquire flock on ``{runtime_dir}/newsroom.lock``; exit 0 if another instance is active."""
    guard = enforce_singleton_or_exit(settings)
    if not guard.is_owner():
        raise RuntimeError("Singleton guard did not become owner (unexpected after enforce)")


def release_runtime_startup_lock(settings: Any | None = None) -> None:
    """Release singleton lock on graceful shutdown."""
    release_singleton_guard()
    if settings is not None:
        try:
            from app.ops.runtime.active_runtime import clear_active_runtime
            import os

            clear_active_runtime(
                str(getattr(settings, "runtime_state_dir", "var/runtime")),
                expected_pid=os.getpid(),
            )
        except Exception as exc:
            logger.warning("active_runtime clear on shutdown failed: %s", exc)


def reset_startup_lock_for_tests() -> None:
    from app.ops.runtime.singleton_guard import reset_singleton_guard_for_tests

    reset_singleton_guard_for_tests()


def startup_lock_path(runtime_dir: str) -> str:
    return str(lock_path_for_runtime(runtime_dir))


def _lock_held_for_tests() -> bool:
    try:
        return get_singleton_guard().is_owner()
    except Exception:
        return False
