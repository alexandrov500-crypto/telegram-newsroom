from __future__ import annotations

from typing import Any


def compute_failure_budgets(
    *,
    pulse: dict[str, Any],
    events: list[dict[str, Any]],
    recovery_log: list[dict[str, Any]],
    degraded_hours_estimate: float = 0.0,
) -> dict[str, Any]:
    """Track accumulated operational stress against soft budgets."""
    lag = float(pulse.get("event_loop_lag_max") or 0)
    recovery = int(pulse.get("recovery_attempt_count") or 0)
    anomalies = len(pulse.get("anomalies") or [])
    alert_events = sum(1 for e in events if e.get("event_type") in ("alert", "posture_change"))

    instability_score = min(1.0, lag / 2.0 + recovery * 0.08 + anomalies * 0.1)
    alert_volume = alert_events + anomalies
    recovery_storm = recovery >= 6

    budgets = {
        "runtime_instability": {
            "used": round(instability_score, 3),
            "budget": 1.0,
            "exhausted": instability_score >= 0.85,
        },
        "alert_volume": {
            "used": alert_volume,
            "budget": 20,
            "exhausted": alert_volume >= 18,
        },
        "recovery_frequency": {
            "used": recovery,
            "budget": 5,
            "exhausted": recovery >= 5,
        },
        "degraded_runtime_hours": {
            "used": round(degraded_hours_estimate, 2),
            "budget": 12.0,
            "exhausted": degraded_hours_estimate >= 10.0,
        },
        "instability_ratio": instability_score,
        "recovery_storm": recovery_storm,
    }

    repeated = sum(1 for r in recovery_log if r.get("outcome") == "repeated")
    budgets["repeated_recoveries"] = repeated

    return budgets
