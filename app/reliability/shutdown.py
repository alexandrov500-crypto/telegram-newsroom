"""Graceful shutdown coordinator (SIGTERM / SIGINT)."""

from __future__ import annotations

import asyncio
import logging
import signal
import threading
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)

_hooks: list[Callable[[], Awaitable[None]]] = []
_registered = False
_lock = threading.Lock()
_shutting_down = False
DRAIN_TIMEOUT_SEC = 30.0


def register_shutdown_hook(coro_fn: Callable[[], Awaitable[None]]) -> None:
    _hooks.append(coro_fn)


def request_graceful_shutdown() -> None:
    global _shutting_down
    _shutting_down = True


def is_shutting_down() -> bool:
    return _shutting_down


def install_signal_handlers(loop: asyncio.AbstractEventLoop | None = None) -> None:
    global _registered
    with _lock:
        if _registered:
            return
        _registered = True

    def _handler(signum: int, _frame: Any) -> None:
        request_graceful_shutdown()
        logger.info("graceful shutdown requested signal=%s", signum)
        try:
            lp = loop or asyncio.get_event_loop()
            if lp.is_running():
                lp.create_task(run_graceful_shutdown())
        except RuntimeError:
            pass

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handler)
        except (ValueError, OSError):
            pass


async def run_graceful_shutdown(settings: Any | None = None) -> None:
    """Stop intake, drain hooks, flush buffers, persist checkpoint."""
    if not _shutting_down:
        request_graceful_shutdown()
    logger.info("graceful shutdown phase=drain_hooks")
    try:
        await asyncio.wait_for(_run_hooks(), timeout=DRAIN_TIMEOUT_SEC)
    except asyncio.TimeoutError:
        logger.warning("graceful shutdown drain timeout exceeded")

    if settings is not None:
        rd = getattr(settings, "runtime_state_dir", None)
        try:
            from app.observability.execution_graph_trace import flush_active_traces_on_shutdown

            n = flush_active_traces_on_shutdown(rd)
            if n:
                logger.info("execution graph traces flushed on shutdown count=%s", n)
        except Exception as exc:
            logger.warning("execution graph shutdown flush failed: %s", exc)

    try:
        from app.observability.event_buffer import get_event_buffer

        if settings is not None:
            get_event_buffer(getattr(settings, "runtime_state_dir", None)).flush(force=True)
        else:
            get_event_buffer(None).flush(force=True)
    except Exception as exc:
        logger.warning("event buffer flush failed: %s", exc)

    if settings is not None:
        try:
            from ops.pipeline.checkpoint_store import save_checkpoint

            save_checkpoint(
                getattr(settings, "runtime_state_dir", None),
                {"last_stable_state": "shutdown"},
            )
        except Exception as exc:
            logger.warning("checkpoint save on shutdown failed: %s", exc)
        try:
            from app.reliability.sqlite_safety import sqlite_safety_pass

            sqlite_safety_pass(settings)
        except Exception as exc:
            logger.warning("sqlite safety on shutdown skipped: %s", exc)
        try:
            from app.reliability.sqlite_backup import backup_sqlite_database

            backup_sqlite_database(runtime_dir=getattr(settings, "runtime_state_dir", None))
        except Exception as exc:
            logger.warning("sqlite backup on shutdown skipped: %s", exc)

    logger.info("graceful shutdown completed")


async def _run_hooks() -> None:
    for hook in list(_hooks):
        try:
            await hook()
        except Exception as exc:
            logger.warning("shutdown hook failed: %s", exc)


def reset_shutdown_for_tests() -> None:
    global _registered, _shutting_down
    _hooks.clear()
    _registered = False
    _shutting_down = False
