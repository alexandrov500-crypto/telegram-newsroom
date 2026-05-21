"""Adaptive throughput controls (bounded, observable)."""

from __future__ import annotations

import time
from typing import Any

from app.runtime_activity import seconds_since_scheduler_tick
from editorial.intelligence_store import load_json, save_json
from ops.economics.paths import throughput_state_path
from utils.metrics import export_snapshot


def _compute_pressure(settings: Any) -> dict[str, float]:
    snap = export_snapshot()
    ctr = dict(snap.get("counters") or {})
    gauges = dict(snap.get("gauges") or {})
    qdepth = float(gauges.get("queue_depth") or 0)
    max_q = float(getattr(settings, "job_queue_max_size", 500) or 500)
    queue_p = min(1.0, qdepth / max(1.0, max_q))
    sched_lag = seconds_since_scheduler_tick()
    sched_lag_f = float(sched_lag) if sched_lag is not None else 0.0
    sched_p = min(1.0, sched_lag_f / max(60.0, float(getattr(settings, "pipeline_interval_minutes", 15) * 60)))
    openai_lat = float(gauges.get("ai_last_cluster_latency_sec") or 0)
    openai_p = min(1.0, openai_lat / 45.0)
    overflow = int(ctr.get("queue_overflow_total") or 0)
    burst_p = min(1.0, overflow / 10.0)
    composite = round(min(1.0, max(queue_p, sched_p * 0.9, openai_p * 0.7, burst_p * 0.5)), 4)
    return {
        "queue_pressure": round(queue_p, 4),
        "scheduler_lag_pressure": round(sched_p, 4),
        "openai_latency_pressure": round(openai_p, 4),
        "source_burst_pressure": round(burst_p, 4),
        "composite": composite,
    }


def compute_adaptations(settings: Any, runtime_dir: str) -> dict[str, Any]:
    from ops.economics.economic_mode import load_economic_mode

    pressure = _compute_pressure(settings)
    mode = load_economic_mode(runtime_dir)
    p = pressure["composite"]
    # Bounded multipliers
    if p < 0.35:
        summarize_mult, publish_mult, replay, poll_mult = 1.0, 1.0, True, 1.0
    elif p < 0.6:
        summarize_mult, publish_mult, replay, poll_mult = 0.85, 1.0, True, 1.1
    elif p < 0.8:
        summarize_mult, publish_mult, replay, poll_mult = 0.65, 0.9, False, 1.25
    else:
        summarize_mult, publish_mult, replay, poll_mult = 0.45, 0.8, False, 1.5
    if mode.value == "burst_mode":
        summarize_mult = min(1.0, summarize_mult * 1.15)
    if mode.value == "low_cost":
        summarize_mult *= 0.75
    out = {
        "pressure": pressure,
        "adaptations": {
            "summarize_concurrency_factor": round(summarize_mult, 3),
            "publish_concurrency_factor": round(publish_mult, 3),
            "replay_enabled": replay,
            "poll_interval_multiplier": round(poll_mult, 3),
            "max_concurrent_summarize": max(1, int(round(2 * summarize_mult))),
        },
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "economic_mode": mode.value,
    }
    save_json(throughput_state_path(runtime_dir), {"version": 1, **out})
    return out


def throughput_payload(settings: Any, runtime_dir: str) -> dict[str, Any]:
    state = load_json(throughput_state_path(runtime_dir), {})
    if not state.get("adaptations"):
        state = compute_adaptations(settings, runtime_dir)
    return state
