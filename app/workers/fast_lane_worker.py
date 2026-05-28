"""FAST lane worker — critical path, target latency < 5s, no heavy pipeline."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.ops.queues import Lane, get_lane_queues
from app.observability.ops_metrics import FastLaneTimer, record_fast_lane_processed
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


async def run_fast_lane_worker(ctx: Any, *, stop_event: asyncio.Event) -> None:
    """
    Consumes FAST_LANE queue; delegates publish logic to breaking consumer core.
    Never blocks on standard lane processing.
    """
    from app.worker.consumers.breaking_consumer import run_breaking_consumer
    from app.ops.queues import sync_legacy_worker_queues

    reg = get_lane_queues()
    if reg is None:
        return
    sync_legacy_worker_queues()
    log_event(logger, "ops.fast_lane_worker.started", latency_target_sec=5)
    await run_breaking_consumer(ctx, stop_event=stop_event)
