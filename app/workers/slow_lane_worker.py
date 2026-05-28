"""SLOW lane — background / analytics-only drain (no publish pressure)."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from app.ops.queues import get_lane_queues
from app.ops.queues import Lane
from ops.pipeline.paths import runtime_root
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


async def run_slow_lane_worker(ctx: Any, *, stop_event: asyncio.Event) -> None:
    reg = get_lane_queues()
    if reg is None:
        return

    settings = ctx.settings
    backlog = runtime_root(settings.runtime_state_dir) / "slow_lane_backlog.jsonl"
    log_event(logger, "ops.slow_lane_worker.started")

    while not stop_event.is_set():
        item = await reg.slow.pop(timeout=0.75)
        if item is None:
            continue
        try:
            row = {
                "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "news_id": item.get("news_id"),
                "source": item.get("source"),
                "lane": Lane.SLOW.value,
                "reason": item.get("ops_route_reason"),
            }
            backlog.parent.mkdir(parents=True, exist_ok=True)
            with backlog.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
            log_event(logger, "ops.slow_lane.accepted", news_id=item.get("news_id"))
        except Exception as exc:
            logger.warning("slow lane item failed: %s", exc)
        finally:
            reg.slow.task_done()
