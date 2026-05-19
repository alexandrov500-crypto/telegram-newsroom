from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProfileSample:
    name: str
    duration_ms: float
    category: str


@dataclass
class RuntimeProfiler:
    """Deep runtime profiling — hotspots, lag spikes, retry roots."""

    _samples: dict[str, list[float]] = field(default_factory=lambda: defaultdict(list))
    _max_per_key: int = 200

    def record(self, category: str, name: str, duration_ms: float) -> None:
        key = f"{category}:{name}"
        bucket = self._samples[key]
        bucket.append(duration_ms)
        if len(bucket) > self._max_per_key:
            self._samples[key] = bucket[-self._max_per_key :]

    def record_handler(self, name: str, duration_ms: float) -> None:
        self.record("handler", name, duration_ms)

    def record_cognition(self, path: str, duration_ms: float) -> None:
        self.record("cognition", path, duration_ms)

    def record_db(self, query: str, duration_ms: float) -> None:
        self.record("db", query[:48], duration_ms)

    def record_queue(self, queue: str, depth: int) -> None:
        self.record("queue", queue, float(depth))

    def record_event_loop_lag(self, lag_ms: float) -> None:
        self.record("event_loop", "lag", lag_ms)

    def hotspots(self, *, top_n: int = 8) -> list[tuple[str, float, int]]:
        ranked: list[tuple[str, float, int]] = []
        for key, vals in self._samples.items():
            if not vals:
                continue
            avg = sum(vals) / len(vals)
            ranked.append((key, avg, len(vals)))
        ranked.sort(key=lambda x: -x[1])
        return ranked[:top_n]

    def bottleneck_report(self) -> dict[str, Any]:
        hotspots = self.hotspots()
        cognition = [h for h in hotspots if h[0].startswith("cognition:")]
        queues = [h for h in hotspots if h[0].startswith("queue:")]
        handlers = [h for h in hotspots if h[0].startswith("handler:")]
        return {
            "generated_at": time.time(),
            "top_hotspots": [
                {"key": k, "avg_ms": round(a, 1), "samples": n} for k, a, n in hotspots
            ],
            "slowest_cognition": cognition[:3],
            "queue_hotspots": queues[:3],
            "slow_handlers": handlers[:3],
        }

    def summary_text(self) -> str:
        report = self.bottleneck_report()
        lines = ["<b>Runtime profile</b>"]
        for h in report["top_hotspots"][:6]:
            lines.append(f"• {h['key']}: {h['avg_ms']:.0f}ms (n={h['samples']})")
        if not report["top_hotspots"]:
            lines.append("No samples yet — traffic will populate profile.")
        return "\n".join(lines)
