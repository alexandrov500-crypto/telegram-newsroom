from __future__ import annotations

from typing import Any

# Conservative thresholds for canary observation (tune only after baseline exists).
LAG_WARN = 0.5
LAG_CRITICAL = 2.0
RECOVERY_BURST = 5


def detect_anomalies(pulse: dict[str, Any]) -> list[dict[str, Any]]:
    anomalies: list[dict[str, Any]] = []

    lag = float(pulse.get("event_loop_lag_max") or 0.0)
    if lag >= LAG_CRITICAL:
        anomalies.append(
            {
                "level": "critical",
                "code": "event_loop_lag",
                "detail": f"lag_max={lag:.3f}s",
                "action": "/freeze_publishing then inspect /runtime_performance",
            },
        )
    elif lag >= LAG_WARN:
        anomalies.append(
            {
                "level": "warning",
                "code": "event_loop_lag_elevated",
                "detail": f"lag_max={lag:.3f}s",
            },
        )

    stalled = pulse.get("stalled_loops") or []
    if stalled:
        anomalies.append(
            {
                "level": "critical",
                "code": "stalled_loops",
                "detail": str(stalled),
                "action": "/freeze_publishing",
            },
        )

    recovery = int(pulse.get("recovery_attempt_count") or 0)
    if recovery >= RECOVERY_BURST:
        anomalies.append(
            {
                "level": "warning",
                "code": "recovery_burst",
                "detail": f"recovery_attempt_count={recovery}",
            },
        )

    if pulse.get("frozen") and pulse.get("paused"):
        anomalies.append(
            {
                "level": "info",
                "code": "channel_frozen",
                "detail": "publishing frozen/paused (expected after incident)",
            },
        )

    profile = pulse.get("runtime_profile")
    if profile and profile != "minimal_pilot":
        anomalies.append(
            {
                "level": "critical",
                "code": "unexpected_runtime_profile",
                "detail": str(profile),
            },
        )

    return anomalies
