"""High-priority lane: expedited validation, defers heavy clustering to scheduler."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from utils.metrics import inc
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


async def run_high_consumer(ctx: Any, *, stop_event: asyncio.Event) -> None:
    """
    Marks high-priority items for scheduler preference (JSONL backlog).
    Does not block breaking lane; no clustering here.
    """
    from app.worker.queues import high_queue
    from ops.pipeline.paths import runtime_root

    if high_queue is None:
        return

    settings = ctx.settings
    backlog = runtime_root(settings.runtime_state_dir) / "high_priority_backlog.jsonl"

    while not stop_event.is_set():
        try:
            item = await asyncio.wait_for(high_queue.get(), timeout=0.75)
        except asyncio.TimeoutError:
            continue
        except asyncio.CancelledError:
            raise

        try:
            row = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "news_id": item.get("news_id"),
                "source": item.get("source") or item.get("channel_name"),
                "message_id": item.get("message_id"),
                "lane_priority": item.get("lane_priority", "high"),
            }
            backlog.parent.mkdir(parents=True, exist_ok=True)
            with backlog.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            inc("high_lane_processed_total")
            log_event(logger, "high.lane.queued", **row)
        except Exception as exc:
            logger.warning("high consumer failed: %s", exc)
        finally:
            high_queue.task_done()
            from app.worker.router import _refresh_depths

            _refresh_depths()
