"""Lane queue observability (depth, drops, breaking latency)."""

from __future__ import annotations

from typing import Any

from utils.metrics import inc, observe_histogram, set_gauge


def record_queue_depths(*, breaking: int, high: int, normal: int) -> None:
    set_gauge("queue_depth_breaking", float(breaking))
    set_gauge("queue_depth_high", float(high))
    set_gauge("queue_depth_normal", float(normal))


def record_dropped_item() -> None:
    inc("dropped_items_total")


def record_breaking_latency(seconds: float) -> None:
    observe_histogram("breaking_latency_seconds", max(0.0, seconds))


def lane_metrics_snapshot() -> dict[str, Any]:
    from utils.metrics import export_snapshot

    snap = export_snapshot()
    counters = snap.get("counters") or {}
    gauges = snap.get("gauges") or {}
    hist = snap.get("histograms") or {}
    brk = hist.get("breaking_latency_seconds") or {}
    return {
        "queue_depth_breaking": gauges.get("queue_depth_breaking"),
        "queue_depth_high": gauges.get("queue_depth_high"),
        "queue_depth_normal": gauges.get("queue_depth_normal"),
        "dropped_items_total": int(counters.get("dropped_items_total", 0)),
        "breaking_latency_seconds_p50": brk.get("p50"),
        "breaking_lane_published_total": int(counters.get("breaking_lane_published_total", 0)),
        "high_lane_processed_total": int(counters.get("high_lane_processed_total", 0)),
        "normal_lane_processed_total": int(counters.get("normal_lane_processed_total", 0)),
    }
