"""Runtime resilience analysis for stability / PUBLIC GO reports."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.observability.runtime_health import load_health_snapshots
from app.observability.runtime_protection import RuntimeHealthLevel, load_protection_state


def _memory_drift_analysis(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    drifts = [float(s.get("rss_drift_mb") or 0) for s in snapshots if s.get("rss_drift_mb") is not None]
    if not drifts:
        return {"samples": 0, "max_drift_mb": None, "avg_drift_mb": None}
    return {
        "samples": len(drifts),
        "max_drift_mb": round(max(drifts), 2),
        "avg_drift_mb": round(sum(drifts) / len(drifts), 2),
    }


def _latency_trend_analysis(snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    p95 = [float(s.get("p95_tick_duration_sec") or 0) for s in snapshots if s.get("p95_tick_duration_sec")]
    oai = [float(s.get("openai_latency_ms") or 0) for s in snapshots if s.get("openai_latency_ms")]
    pub = [float(s.get("publish_latency_ms") or 0) for s in snapshots if s.get("publish_latency_ms")]
    return {
        "tick_p95_max_sec": round(max(p95), 2) if p95 else None,
        "openai_latency_max_ms": round(max(oai), 1) if oai else None,
        "publish_latency_max_ms": round(max(pub), 1) if pub else None,
    }


def _degradation_incidents(state: dict[str, Any]) -> list[dict[str, Any]]:
    hist = state.get("transition_history") or []
    return [
        h
        for h in hist
        if str(h.get("to")) in {RuntimeHealthLevel.DEGRADED.value, RuntimeHealthLevel.CRITICAL.value}
    ]


def _recovery_loops(state: dict[str, Any], *, window: int = 20) -> int:
    """Count degraded↔normal oscillations in recent transitions."""
    hist = state.get("transition_history") or []
    tail = hist[-window:]
    loops = 0
    for i in range(1, len(tail)):
        a, b = str(tail[i - 1].get("to")), str(tail[i].get("to"))
        if {a, b} == {RuntimeHealthLevel.NORMAL.value, RuntimeHealthLevel.DEGRADED.value}:
            loops += 1
    return loops


def compute_uptime_health_score(snapshots: list[dict[str, Any]], state: dict[str, Any]) -> float:
    if not snapshots:
        return 50.0
    clean = sum(1 for s in snapshots if not (s.get("degradation_flags")))
    ratio = clean / len(snapshots)
    score = 40.0 + ratio * 50.0
    level = str(state.get("current_state") or "normal")
    if level == RuntimeHealthLevel.CRITICAL.value:
        score -= 30.0
    elif level == RuntimeHealthLevel.DEGRADED.value:
        score -= 15.0
    elif level == RuntimeHealthLevel.ELEVATED.value:
        score -= 5.0
    return max(0.0, min(100.0, round(score, 1)))


def build_runtime_resilience_section(runtime_dir: Path, *, snapshot_limit: int = 200) -> dict[str, Any]:
    rd = str(runtime_dir)
    snapshots = load_health_snapshots(rd, limit=snapshot_limit)
    state = load_protection_state(rd)
    critical_in_window = sum(
        1
        for h in (state.get("transition_history") or [])
        if str(h.get("to")) == RuntimeHealthLevel.CRITICAL.value
    )
    return {
        "uptime_health_score": compute_uptime_health_score(snapshots, state),
        "memory_drift": _memory_drift_analysis(snapshots),
        "latency_trends": _latency_trend_analysis(snapshots),
        "degradation_incidents": len(_degradation_incidents(state)),
        "degradation_incident_details": _degradation_incidents(state)[-10:],
        "recovery_count": int(state.get("recovery_count") or 0),
        "protection_activation_count": int(state.get("protection_activation_count") or 0),
        "recovery_loops": _recovery_loops(state),
        "critical_transitions_in_history": critical_in_window,
        "current_protection_state": state.get("current_state"),
        "last_critical_at": state.get("last_critical_at"),
        "health_snapshots_sampled": len(snapshots),
    }


def evaluate_public_go_resilience(runtime_dir: Path) -> tuple[list[str], list[str]]:
    """Return (fail_blockers, warn_notes)."""
    section = build_runtime_resilience_section(runtime_dir)
    fails: list[str] = []
    warns: list[str] = []

    if section.get("current_protection_state") == RuntimeHealthLevel.CRITICAL.value:
        fails.append("runtime_protection_critical_active")

    if int(section.get("critical_transitions_in_history") or 0) > 0:
        fails.append(f"runtime_critical_during_burnin:{section['critical_transitions_in_history']}")

    drift = section.get("memory_drift") or {}
    max_drift = drift.get("max_drift_mb")
    import os

    threshold = float(os.getenv("PUBLIC_GO_MAX_RSS_DRIFT_MB", "384"))
    if max_drift is not None and float(max_drift) > threshold:
        fails.append(f"memory_drift_exceeded:{max_drift}>{threshold}")

    loops = int(section.get("recovery_loops") or 0)
    if loops > int(os.getenv("PUBLIC_GO_MAX_RECOVERY_LOOPS", "3")):
        fails.append(f"recovery_loops_detected:{loops}")

    snapshots = load_health_snapshots(str(runtime_dir), limit=50)
    lag_hits = sum(1 for s in snapshots if "scheduler_lag_high" in (s.get("degradation_flags") or []))
    if lag_hits >= int(os.getenv("PUBLIC_GO_SCHEDULER_LAG_SNAPSHOTS", "5")):
        fails.append(f"sustained_scheduler_lag:{lag_hits}")

    if section.get("current_protection_state") == RuntimeHealthLevel.ELEVATED.value:
        warns.append("runtime_elevated_transient_ok")

    return fails, warns
