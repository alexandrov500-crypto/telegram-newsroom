"""Bounded live-validation harness (deterministic; CI-safe)."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LiveValidationSample:
    name: str
    ok: bool
    duration_sec: float
    metrics: dict[str, Any] = field(default_factory=dict)
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class LiveValidationRun:
    samples: list[LiveValidationSample] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(s.ok for s in self.samples)

    def summary(self) -> dict[str, Any]:
        return {
            "sample_count": len(self.samples),
            "ok": self.ok,
            "samples": [
                {
                    "name": s.name,
                    "ok": s.ok,
                    "duration_sec": s.duration_sec,
                    "metrics": s.metrics,
                    "detail": s.detail,
                }
                for s in self.samples
            ],
        }


def run_bounded(coro_factory, *, name: str, timeout_sec: float = 5.0) -> LiveValidationSample:
    t0 = time.perf_counter()

    async def _wrap() -> Any:
        return await asyncio.wait_for(coro_factory(), timeout=timeout_sec)

    try:
        result = asyncio.run(_wrap())
        return LiveValidationSample(
            name=name,
            ok=True,
            duration_sec=round(time.perf_counter() - t0, 4),
            detail={"result": str(type(result).__name__)},
        )
    except Exception as exc:
        return LiveValidationSample(
            name=name,
            ok=False,
            duration_sec=round(time.perf_counter() - t0, 4),
            detail={"error": repr(exc)},
        )
