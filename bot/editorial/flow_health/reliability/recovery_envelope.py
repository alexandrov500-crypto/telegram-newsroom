from __future__ import annotations

from typing import Any

from bot.editorial.flow_health.state import load_state


def validate_recovery_envelope(
    *,
    adaptive: dict[str, Any] | None = None,
    cadence: dict[str, Any] | None = None,
    degradation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Verify recovery stays within bounded operational envelope."""
    adaptive = adaptive or {}
    relax = adaptive.get("relaxation") or {}
    cadence = cadence or {}
    degradation = degradation or {}

    max_scale = float(relax.get("effective_scale") or 0)
    budget_used = float(relax.get("relaxation_budget_used") or 0)
    budget_max = float(relax.get("relaxation_budget_max") or 0.25)

    st = load_state()
    hist = list(st.get("degradation_mode_history") or [])
    escalations = 0
    prev = "NORMAL"
    for h in hist[-10:]:
        mode = str(h.get("mode", "NORMAL"))
        if mode != prev and mode not in ("NORMAL", prev):
            escalations += 1
        prev = mode

    ch = float(cadence.get("cadence_health") or 1.0)
    oscillation = 0.75 <= ch <= 1.15 and bool(hist) and escalations >= 2

    saturated = budget_max > 0 and budget_used >= budget_max * 0.92
    healthy = not saturated and max_scale <= 0.55 and escalations <= 2 and not oscillation

    return {
        "recovery_envelope_health": "healthy" if healthy else "stressed",
        "max_effective_scale": round(max_scale, 3),
        "cumulative_relaxation_pressure": round(budget_used, 3),
        "budget_saturation": saturated,
        "degradation_escalations_recent": escalations,
        "cadence_oscillation_suspected": oscillation,
        "envelope_within_bounds": healthy,
    }
