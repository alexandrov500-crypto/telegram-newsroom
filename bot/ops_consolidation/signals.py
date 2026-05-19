from __future__ import annotations

from typing import Any


# Overlapping concerns → single canonical owner (advisory routing).
CANONICAL_SIGNAL_OWNERS: dict[str, str] = {
    "event_loop_lag": "runtime",
    "stalled_loops": "runtime",
    "recovery_attempt": "runtime",
    "soft_degraded": "resilience",
    "posture_change": "resilience",
    "fatigue_warning": "editorial_quality",
    "phrase_fatigue": "editorial_quality",
    "storyline_saturation": "editorial_memory",
    "priority_drift": "prioritization",
    "trust_band_decay": "trust_calibration",
    "warning_precision": "trust_calibration",
    "operational_drift": "observation",
    "storage_pressure": "lifecycle",
    "attention_noise": "operator_ux",
    "weekly_tuning_hint": "evidence_review",
}


OVERLAP_GROUPS: list[dict[str, Any]] = [
    {
        "concern": "runtime_lag",
        "sources": [
            "observation_pulse.event_loop_lag_max",
            "loop_health.event_loop_lag",
            "resilience.forecast.lag_trend",
            "operator_digest lag line",
        ],
        "canonical": "observation_pulse",
        "action": "prefer /resilience_status + pulse; suppress duplicate lag in digest",
    },
    {
        "concern": "fatigue",
        "sources": [
            "editorial_quality.fatigue",
            "editorial_memory.saturation",
            "trust_calibration.fatigue_detection",
            "evidence_review.fatigue_hotspots",
        ],
        "canonical": "editorial_quality.fatigue",
        "action": "memory saturation only when storyline-linked",
    },
    {
        "concern": "drift",
        "sources": [
            "editorial_quality.drift",
            "editorial_priority.drift",
            "ops_forensics.drift",
            "trust_calibration.confidence_drift",
        ],
        "canonical": "per-domain drift (quality vs priority vs trust)",
        "action": "do not merge; dedupe display labels in operator UX",
    },
    {
        "concern": "trust_reliability",
        "sources": [
            "trust_calibration.subsystems",
            "evidence_review.signal_effectiveness",
            "resilience.failure_budgets",
        ],
        "canonical": "trust_calibration for live; evidence_review for weekly",
        "action": "weekly review references trust snapshot, does not recompute",
    },
    {
        "concern": "recovery",
        "sources": [
            "loop_health.recovery_attempt_count",
            "resilience.recovery_quality",
            "runtime soft_degradation",
        ],
        "canonical": "resilience.recovery_quality",
        "action": "loop_health count is input only",
    },
]


def analyze_signal_overlap() -> dict[str, Any]:
    return {
        "canonical_owners": CANONICAL_SIGNAL_OWNERS,
        "overlap_groups": OVERLAP_GROUPS,
        "consolidation_recommendations": [g["action"] for g in OVERLAP_GROUPS],
    }


def dedupe_context_signals(ctx: dict[str, Any]) -> dict[str, Any]:
    """
    Lightweight dedupe for operator digest/dashboard — suppress redundant fields
    when canonical source already present in pulse.
    """
    pulse = ctx.get("pulse") or {}
    if not pulse:
        return ctx

    out = dict(ctx)
    drift = dict(out.get("priority_drift") or {})
    if pulse.get("event_loop_lag_max") is not None:
        drift.pop("lag_duplicate", None)
    if drift.get("drift_alert") == "stable" and not drift.get("warnings"):
        out["priority_drift"] = {"drift_alert": "stable", "note": "see trust_calibration for subsystem drift"}
    else:
        out["priority_drift"] = drift

    anomalies = pulse.get("anomalies") or []
    if anomalies and out.get("live_incidents"):
        out["live_incidents"] = (out.get("live_incidents") or [])[:5]

    out["_signals_deduped"] = True
    return out
