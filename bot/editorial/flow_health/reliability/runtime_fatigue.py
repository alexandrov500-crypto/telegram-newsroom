from __future__ import annotations

from typing import Any

from bot.editorial.flow_health.state import load_state


def compute_runtime_fatigue(
    *,
    degradation: dict[str, Any] | None = None,
    hygiene: dict[str, Any] | None = None,
    durability: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Detect slow operational exhaustion over long uptime."""
    st = load_state()
    signals: list[str] = []
    points = 0

    hist = list(st.get("degradation_mode_history") or [])
    non_normal = sum(1 for h in hist if str(h.get("mode", "NORMAL")) != "NORMAL")
    if len(hist) >= 6 and non_normal >= len(hist) * 0.5:
        points += 2
        signals.append("frequent_degradation_modes")

    if st.get("low_observability_active"):
        points += 1
        signals.append("low_observability_active")

    immune = (durability or {}).get("baseline_immunity") or {}
    if immune.get("immunity_active"):
        points += 1
        signals.append("baseline_immunity_engaged")

    minimize = (hygiene or {}).get("state_minimize") or {}
    if int(minimize.get("bytes_reduced") or 0) == 0 and float(
        minimize.get("adaptive_state_weight") or 0,
    ) >= 0.6:
        points += 1
        signals.append("heavy_adaptive_state")

    relax_hist = [float(x) for x in (st.get("relaxation_budget_history") or [])][-12:]
    if len(relax_hist) >= 6:
        avg = sum(relax_hist) / len(relax_hist)
        if avg >= 0.18:
            points += 1
            signals.append("sustained_relaxation_pressure")

    score = round(min(1.0, points / 6.0), 3)
    band = "LOW"
    if score >= 0.55:
        band = "HIGH"
    elif score >= 0.32:
        band = "MODERATE"

    return {
        "runtime_fatigue_score": score,
        "runtime_fatigue_band": band,
        "fatigue_signals": signals,
    }
