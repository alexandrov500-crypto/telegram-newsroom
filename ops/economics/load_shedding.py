"""Graceful load shedding under pressure (preserves publish integrity + audit)."""

from __future__ import annotations

import time
from typing import Any

from editorial.intelligence_store import load_json, save_json
from ops.economics.budgets import budget_pressure
from ops.economics.paths import load_shedding_path
from ops.economics.throughput import compute_adaptations


def evaluate_load_shedding(settings: Any, runtime_dir: str) -> dict[str, Any]:
    tp = compute_adaptations(settings, runtime_dir)
    pressure = float((tp.get("pressure") or {}).get("composite") or 0)
    bpressure = budget_pressure(runtime_dir)
    composite = min(1.0, max(pressure, bpressure))
    active: list[str] = []
    flags = {
        "low_priority_source_suppression": composite >= 0.55,
        "reduced_summarize_depth": composite >= 0.65,
        "replay_paused": composite >= 0.75 or not (tp.get("adaptations") or {}).get("replay_enabled", True),
        "analytics_throttled": composite >= 0.5,
        "notification_throttled": composite >= 0.8,
    }
    for k, v in flags.items():
        if v:
            active.append(k)
    state = {
        "version": 1,
        "composite_pressure": round(composite, 4),
        "active_measures": active,
        "flags": flags,
        "publish_integrity_preserved": True,
        "audit_preserved": True,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    save_json(load_shedding_path(runtime_dir), state)
    return state


def should_skip_summarize_for_pressure(
    settings: Any,
    runtime_dir: str,
    *,
    priority_level: str = "medium",
) -> tuple[bool, str]:
    state = evaluate_load_shedding(settings, runtime_dir)
    pri = str(priority_level or "medium").lower()
    if state["flags"].get("low_priority_source_suppression") and pri == "low":
        return True, "load_shed_low_priority"
    if state["composite_pressure"] >= 0.9 and pri not in ("high", "breaking", "critical"):
        return True, "load_shed_high_pressure"
    return False, "ok"


def summarize_depth_factor(runtime_dir: str, settings: Any) -> float:
    state = load_json(load_shedding_path(runtime_dir), {})
    if state.get("flags", {}).get("reduced_summarize_depth"):
        return 0.6
    from ops.economics.economic_mode import load_economic_mode

    prof = load_economic_mode(runtime_dir)
    if prof.value == "low_cost":
        return 0.7
    if prof.value == "high_quality":
        return 1.0
    return 0.85
