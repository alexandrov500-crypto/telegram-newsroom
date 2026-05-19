from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from bot.observability.loop_diagnostics import timed_async_job
from bot.observability.registry import ObservabilityRegistry
from bot.runtime.profile import get_runtime_capabilities

logger = logging.getLogger(__name__)


async def run_minimal_pilot_ops_loop(
    *,
    registry: ObservabilityRegistry,
    controlled_live: Any,
) -> None:
    """Lightweight ops loop: controlled live tick + metrics only."""
    from bot.observability.loop_registry import get_loop_registry

    caps = get_runtime_capabilities()
    loop_reg = get_loop_registry()
    loop_reg.register("pilot-ops", float(caps.ops_loop_interval_sec))
    interval = caps.ops_loop_interval_sec

    while True:
        started = time.perf_counter()
        err: str | None = None
        try:
            async with timed_async_job("minimal-pilot-ops"):
                backlog = registry.queue_backlog()
                signals = {
                    "queue_depth": backlog,
                    "publish_fatigue": 0.2,
                    "engagement_quality": 0.75,
                }
                if controlled_live is not None:
                    await controlled_live.tick(signals=signals)
                    logger.debug(
                        "event=minimal_pilot_ops_tick mode=%s frozen=%s",
                        (controlled_live.repository.get_state() or {}).get("live_mode"),
                        (controlled_live.repository.get_state() or {}).get("frozen"),
                    )
        except Exception:
            err = "tick_failed"
            logger.exception("event=minimal_pilot_ops_tick_failed")
        finally:
            loop_reg.heartbeat(
                "pilot-ops",
                time.perf_counter() - started,
                error=err,
            )
        await asyncio.sleep(interval)
