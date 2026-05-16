"""Lightweight resource stability snapshots (no mandatory profilers)."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from utils.diagnostics import rss_bytes_best_effort


@dataclass
class ResourceSnapshot:
    ts: str
    rss_bytes: int | None
    asyncio_tasks: int
    open_fds: int | None = None


def snapshot_resources() -> ResourceSnapshot:
    tasks = 0
    try:
        import asyncio

        try:
            loop = asyncio.get_running_loop()
            tasks = len(asyncio.all_tasks(loop))
        except RuntimeError:
            tasks = 0
    except Exception:
        tasks = 0

    fds: int | None = None
    try:
        import resource

        fds = int(resource.getrlimit(resource.RLIMIT_NOFILE)[0])
    except Exception:
        fds = None

    return ResourceSnapshot(
        ts=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        rss_bytes=rss_bytes_best_effort(),
        asyncio_tasks=tasks,
        open_fds=fds,
    )


def analyze_memory_trend(
    samples: list[ResourceSnapshot], *, warn_pct: float = 35.0
) -> dict[str, Any]:
    rss_vals = [s.rss_bytes for s in samples if s.rss_bytes is not None]
    if len(rss_vals) < 2:
        return {"status": "insufficient_data", "samples": len(samples)}
    first, last = rss_vals[0], rss_vals[-1]
    growth = 0.0 if first <= 0 else 100.0 * (last - first) / first
    status = "WARNING" if growth >= warn_pct else "OK"
    return {
        "status": status,
        "samples": len(samples),
        "rss_first": first,
        "rss_last": last,
        "growth_pct": round(growth, 2),
    }


def analyze_task_growth(samples: list[ResourceSnapshot], *, warn_delta: int = 50) -> dict[str, Any]:
    if len(samples) < 2:
        return {"status": "insufficient_data"}
    delta = samples[-1].asyncio_tasks - samples[0].asyncio_tasks
    status = "WARNING" if delta >= warn_delta else "OK"
    return {
        "status": status,
        "task_delta": delta,
        "first": samples[0].asyncio_tasks,
        "last": samples[-1].asyncio_tasks,
    }


def write_resource_report(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path
