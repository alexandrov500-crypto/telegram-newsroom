"""Start/stop multi-lane ingestion workers (ops layer)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.ops.priority_router import ops_lanes_enabled
from app.ops.priority_router import breaking_only_mode
from app.ops.queues import init_lane_queues, sync_legacy_worker_queues
from app.workers import run_fast_lane_worker, run_slow_lane_worker, run_standard_lane_worker
from utils.structured_log import log_event

logger = logging.getLogger(__name__)

_stop_event: asyncio.Event | None = None
_tasks: list[asyncio.Task[None]] = []


def fast_lane_enabled() -> bool:
    return ops_lanes_enabled()


def start_lane_workers(ctx: Any) -> None:
    """Initialize ops queues and spawn isolated lane workers."""
    global _stop_event, _tasks

    if not ops_lanes_enabled():
        log_event(logger, "lane.workers.disabled", reason="FAST_LANE_ENABLED=false")
        return

    init_lane_queues()
    sync_legacy_worker_queues()

    from app.runtime.task_orchestrator import create_traced_task

    _stop_event = asyncio.Event()
    _tasks = [
        create_traced_task(
            "ops-fast-lane",
            run_fast_lane_worker(ctx, stop_event=_stop_event),
            trace_id="lane-fast",
            owner="lane_runtime",
            metadata={"task_type": "lane_worker"},
            name="ops-fast-lane",
        ),
    ]
    if not breaking_only_mode():
        _tasks.append(
            create_traced_task(
                "ops-standard-lane",
                run_standard_lane_worker(ctx, stop_event=_stop_event),
                trace_id="lane-standard",
                owner="lane_runtime",
                metadata={"task_type": "lane_worker"},
                name="ops-standard-lane",
            )
        )
        _tasks.append(
            create_traced_task(
                "ops-slow-lane",
                run_slow_lane_worker(ctx, stop_event=_stop_event),
                trace_id="lane-slow",
                owner="lane_runtime",
                metadata={"task_type": "lane_worker"},
                name="ops-slow-lane",
            )
        )

    log_event(
        logger,
        "ops.lane_workers.started",
        breaking_only=breaking_only_mode(),
        lanes=["fast", "standard", "slow"] if not breaking_only_mode() else ["fast"],
    )


async def stop_lane_workers() -> None:
    global _stop_event, _tasks
    if _stop_event is not None:
        _stop_event.set()
    for t in _tasks:
        if t is not None:
            t.cancel()
    live = [t for t in _tasks if t is not None]
    if live:
        await asyncio.gather(*live, return_exceptions=True)
    _tasks = []
    _stop_event = None
    from app.ops.queues import reset_lane_queues_for_tests
    from app.worker import queues as legacy

    reset_lane_queues_for_tests()
    legacy.reset_lane_queues_for_tests()
    log_event(logger, "ops.lane_workers.stopped")
