"""Standard lane: acknowledges routed items; full pipeline remains scheduler-driven."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from utils.metrics import inc
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


async def run_normal_consumer(ctx: Any, *, stop_event: asyncio.Event) -> None:
    """
    Drains normal queue for backpressure + observability.
    Raw posts are already in DB; scheduler tick runs clustering / desk / draft.
    """
    from app.worker.queues import normal_queue

    if normal_queue is None:
        return

    while not stop_event.is_set():
        try:
            item = await asyncio.wait_for(normal_queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            continue
        except asyncio.CancelledError:
            raise

        try:
            inc("normal_lane_processed_total")
            log_event(
                logger,
                "normal.lane.accepted",
                news_id=item.get("news_id"),
                source=item.get("source") or item.get("channel_name"),
                lane_priority=item.get("lane_priority", "normal"),
            )
        except Exception as exc:
            logger.warning("normal consumer failed: %s", exc)
        finally:
            normal_queue.task_done()
            from app.worker.router import _refresh_depths

            _refresh_depths()
