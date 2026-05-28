"""OPS metrics for multi-lane ingestion (SLA / lag / routing)."""

from __future__ import annotations

import time
from typing import Any

from utils.metrics import inc, observe_histogram, set_gauge


def record_queue_depths(*, fast: int, standard: int, slow: int) -> None:
    set_gauge("fast_lane_queue_depth", float(fast))
    set_gauge("standard_lane_queue_depth", float(standard))
    set_gauge("slow_lane_queue_depth", float(slow))


def record_routing_decision(lane: str) -> None:
    inc(f"routing_decision_{lane}_total")


def record_overflow(lane: str) -> None:
    inc("dropped_due_to_overflow_total")
    inc(f"lane_overflow_{lane}_total")


def record_fast_lane_latency_ms(ms: float) -> None:
    observe_histogram("fast_lane_latency_ms", max(0.0, ms) / 1000.0)


def record_fast_lane_processed() -> None:
    inc("fast_lane_processed_total")


class FastLaneTimer:
    def __init__(self) -> None:
        self._t0 = time.perf_counter()

    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self._t0) * 1000.0

    def finish(self) -> float:
        ms = self.elapsed_ms()
        record_fast_lane_latency_ms(ms)
        return ms


def ops_snapshot() -> dict[str, Any]:
    from utils.metrics import export_snapshot

    snap = export_snapshot()
    c = snap.get("counters") or {}
    g = snap.get("gauges") or {}
    h = snap.get("histograms") or {}
    lat = h.get("fast_lane_latency_ms") or {}
    return {
        "fast_lane_queue_depth": g.get("fast_lane_queue_depth"),
        "standard_lane_queue_depth": g.get("standard_lane_queue_depth"),
        "slow_lane_queue_depth": g.get("slow_lane_queue_depth"),
        "fast_lane_processed_total": int(c.get("fast_lane_processed_total", 0)),
        "dropped_due_to_overflow_total": int(c.get("dropped_due_to_overflow_total", 0)),
        "routing_decision_fast_total": int(c.get("routing_decision_fast_total", 0)),
        "routing_decision_standard_total": int(c.get("routing_decision_standard_total", 0)),
        "routing_decision_slow_total": int(c.get("routing_decision_slow_total", 0)),
        "fast_lane_latency_ms_p50": lat.get("p50"),
    }
