"""Periodic economics maintenance (heartbeat)."""

from __future__ import annotations

from typing import Any


def run_economics_tick(settings: Any, *, logger: Any = None) -> dict[str, Any]:
    rd = settings.runtime_state_dir
    from ops.economics.roi import update_roi_daily
    from ops.economics.slo import compute_slo_status
    from ops.economics.storage import assess_storage
    from ops.economics.throughput import compute_adaptations
    from ops.economics.load_shedding import evaluate_load_shedding

    storage = assess_storage(rd, logger_obj=logger)
    throughput = compute_adaptations(settings, rd)
    shedding = evaluate_load_shedding(settings, rd)
    roi = update_roi_daily(rd)
    slo = compute_slo_status(settings, rd)
    return {
        "storage_pressure": storage.get("pressure"),
        "throughput_composite": (throughput.get("pressure") or {}).get("composite"),
        "load_shedding": shedding.get("active_measures"),
        "slo_ok": slo.get("aggregate_ok"),
        "roi_publish_proxy": roi.get("publish_usefulness_proxy"),
    }
