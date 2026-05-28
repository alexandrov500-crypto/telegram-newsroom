"""Asyncio priority lanes with bounded backpressure."""

from __future__ import annotations

import asyncio
import os
from typing import Any

_DEFAULT_BREAKING = int(os.getenv("LANE_QUEUE_BREAKING_MAX", "32"))
_DEFAULT_HIGH = int(os.getenv("LANE_QUEUE_HIGH_MAX", "128"))
_DEFAULT_NORMAL = int(os.getenv("LANE_QUEUE_NORMAL_MAX", "512"))

breaking_queue: asyncio.Queue[dict[str, Any]] | None = None
high_queue: asyncio.Queue[dict[str, Any]] | None = None
normal_queue: asyncio.Queue[dict[str, Any]] | None = None


def init_lane_queues(
    *,
    breaking_max: int | None = None,
    high_max: int | None = None,
    normal_max: int | None = None,
) -> None:
    global breaking_queue, high_queue, normal_queue
    breaking_queue = asyncio.Queue(maxsize=max(1, breaking_max or _DEFAULT_BREAKING))
    high_queue = asyncio.Queue(maxsize=max(1, high_max or _DEFAULT_HIGH))
    normal_queue = asyncio.Queue(maxsize=max(1, normal_max or _DEFAULT_NORMAL))


def reset_lane_queues_for_tests() -> None:
    global breaking_queue, high_queue, normal_queue
    breaking_queue = None
    high_queue = None
    normal_queue = None


def queue_depths() -> dict[str, int]:
    return {
        "breaking": breaking_queue.qsize() if breaking_queue else 0,
        "high": high_queue.qsize() if high_queue else 0,
        "normal": normal_queue.qsize() if normal_queue else 0,
    }
