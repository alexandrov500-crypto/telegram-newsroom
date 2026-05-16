"""Worker role, signal wiring, and shared logging helpers."""

from __future__ import annotations

import asyncio
import logging
import signal
from enum import Enum
from typing import Any

from utils.structured_log import log_event

logger = logging.getLogger(__name__)


class WorkerRole(str, Enum):
    INGEST = "ingest"
    AI = "ai"
    PUBLISHER = "publisher"


def install_shutdown_signals(shutdown: asyncio.Event, *, worker_role: str, instance_id: str) -> None:
    """SIGTERM/SIGINT → cooperative shutdown (Unix). Windows: no-op."""
    loop = asyncio.get_running_loop()

    def _handler() -> None:
        if not shutdown.is_set():
            log_event(
                logger,
                "worker.shutdown_signal",
                worker_role=worker_role,
                worker_instance_id=instance_id,
            )
        shutdown.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _handler)
        except (NotImplementedError, RuntimeError):
            log_event(logger, "worker.signal_handler_unavailable", signal=str(sig))


def worker_log_extra(settings: Any) -> dict[str, Any]:
    return {
        "worker_instance_id": getattr(settings, "worker_instance_id", ""),
        "deployment_profile": getattr(settings, "deployment_profile", ""),
    }
