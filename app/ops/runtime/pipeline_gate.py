"""Pipeline processing gate — singleton owner + OPS halt."""

from __future__ import annotations

import logging
from typing import Any

from app.ops.control_plane.guards import emergency_halt_active
from app.ops.runtime import singleton_guard as _sg

logger = logging.getLogger(__name__)


def _runtime_id() -> str:
    try:
        from app.runtime_lifecycle import runtime_id

        return runtime_id()
    except Exception:
        return "unknown"


def is_singleton_owner() -> bool:
    import os

    if os.getenv("RUNTIME_SINGLETON_DISABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return True
    guard = _sg._guard  # noqa: SLF001 — intentional owner check
    return guard is not None and guard.is_owner()


def allow_processing() -> tuple[bool, str]:
    """
    ALLOW_PROCESSING only when this process holds the singleton lock and OPS is not halted.
    """
    if not is_singleton_owner():
        return False, "not_singleton_owner"
    if emergency_halt_active():
        return False, "emergency_halt"
    return True, "ok"


def log_gate_blocked(reason: str, **extra: Any) -> None:
    logger.info(
        "[GATE] blocked runtime_id=%s reason=%s %s",
        _runtime_id(),
        reason,
        extra or "",
    )


def require_processing_or_skip(*, component: str) -> bool:
    """Return True if processing may continue; logs and returns False otherwise."""
    ok, reason = allow_processing()
    if ok:
        return True
    log_gate_blocked(reason, component=component)
    return False
