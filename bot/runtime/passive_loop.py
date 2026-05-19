from __future__ import annotations

import asyncio
import logging
import time

from bot.observability.loop_registry import get_loop_registry
from bot.runtime.profile import get_runtime_capabilities

logger = logging.getLogger(__name__)


async def run_passive_heartbeat_loop(loop_name: str) -> None:
    """Register periodic heartbeats without doing work (research loops disabled)."""
    caps = get_runtime_capabilities()
    interval = caps.passive_loop_interval_sec
    loop_reg = get_loop_registry()
    loop_reg.register(loop_name, float(interval) * 2.5)

    while True:
        started = time.perf_counter()
        loop_reg.heartbeat(loop_name, time.perf_counter() - started)
        logger.debug("event=passive_loop_heartbeat loop=%s", loop_name)
        await asyncio.sleep(interval)
