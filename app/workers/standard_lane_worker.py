"""STANDARD lane — full pipeline via DB + scheduler (queue ack + priority backlog)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.ops.queues import Lane, get_lane_queues
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


async def run_standard_lane_worker(ctx: Any, *, stop_event: asyncio.Event) -> None:
    """
    Drains standard queue: persists priority hints for scheduler.
    Does NOT run clustering here (scheduler tick owns cold path).
    """
    from app.worker.consumers.high_consumer import run_high_consumer

    reg = get_lane_queues()
    if reg is None:
        return

    log_event(logger, "ops.standard_lane_worker.started")
    # high_consumer writes priority backlog — map standard lane to same behavior
    await run_high_consumer(ctx, stop_event=stop_event)
