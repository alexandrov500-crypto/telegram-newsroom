"""Periodic low-noise operational summary for long-running deployments."""

from __future__ import annotations

import logging
from typing import Any

from app.openai_circuit import get_openai_circuit
from app.runtime_lifecycle import emit_lifecycle, runtime_id, uptime_sec
from ops.runtime_timeline import watchdog_alerts_total
from utils.diagnostics import rss_bytes_best_effort
from utils.metrics import export_snapshot
from utils.structured_log import log_event

logger = logging.getLogger(__name__)


def log_soak_operational_summary(settings: Any) -> None:
    snap = export_snapshot()
    ctr = snap.get("counters") or {}
    gauges = snap.get("gauges") or {}
    hist = snap.get("histograms") or {}
    sched = hist.get("scheduler_cycle_duration_seconds") or {}
    collect = hist.get("collect_duration_seconds") or {}
    circuit = get_openai_circuit().snapshot()

    fields = {
        "subsystem": "soak",
        "runtime_id": runtime_id(),
        "uptime_sec": round(uptime_sec(), 1),
        "rss_bytes": rss_bytes_best_effort(),
        "queue_depth": int(gauges.get("queue_depth", 0)),
        "queue_overflow_total": int(ctr.get("queue_overflow_total", 0)),
        "scheduler_cycles": int(sched.get("count", 0)),
        "scheduler_cycle_avg_sec": (
            round(float(sched.get("sum", 0)) / max(1, int(sched.get("count", 1))), 3)
            if sched.get("count")
            else None
        ),
        "collector_runs": int(collect.get("count", 0)),
        "posts_collected_total": int(ctr.get("posts_collected", 0)),
        "openai_circuit_state": circuit.get("state"),
        "openai_failures_total": int(ctr.get("openai_failures_total", 0)),
        "watchdog_alerts_total": watchdog_alerts_total(),
        "degraded_transitions": int(ctr.get("degraded_state_transitions_total", 0)),
    }
    log_event(logger, "ops.soak.summary", **fields)
    emit_lifecycle("ops.soak.summary", **{k: v for k, v in fields.items() if v is not None})
