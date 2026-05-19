from __future__ import annotations

from typing import Any

from bot.editorial.flow_health.state import load_state


def compute_recovery_calmness(
    *,
    recovery_envelope: dict[str, Any] | None = None,
    degradation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Recovery should be quiet — low transition churn and oscillation."""
    st = load_state()
    hist = list(st.get("degradation_mode_history") or [])
    transitions = 0
    prev = None
    for h in hist[-12:]:
        mode = str(h.get("mode", "NORMAL"))
        if prev and mode != prev:
            transitions += 1
        prev = mode

    env = recovery_envelope or {}
    oscillation = bool(env.get("cadence_oscillation_suspected"))
    saturated = bool(env.get("budget_saturation"))
    volatile = transitions >= 4 or oscillation

    calmness = 1.0
    if transitions >= 2:
        calmness -= 0.15 * min(3, transitions - 1)
    if oscillation:
        calmness -= 0.2
    if saturated:
        calmness -= 0.15
    if str((degradation or {}).get("mode")) not in ("NORMAL",):
        calmness -= 0.1

    score = round(max(0.0, min(1.0, calmness)), 3)
    band = "CALM"
    if score < 0.55:
        band = "VOLATILE"
    elif score < 0.72:
        band = "UNEASY"

    return {
        "recovery_calmness_score": score,
        "recovery_calmness_band": band,
        "mode_transitions_recent": transitions,
        "oscillation_suspected": oscillation,
    }
