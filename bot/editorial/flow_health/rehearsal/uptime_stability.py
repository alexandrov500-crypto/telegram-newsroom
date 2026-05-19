from __future__ import annotations

from typing import Any

from bot.editorial.flow_health.state import load_state


def validate_uptime_stability(
    *,
    reliability: dict[str, Any] | None = None,
    slimming: dict[str, Any] | None = None,
    degradation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Weeks-long uptime instability proxies — advisory."""
    st = load_state()
    signals: list[str] = []
    points = 0

    hist = list(st.get("degradation_mode_history") or [])
    if len(hist) >= 8:
        non_normal = sum(1 for h in hist if str(h.get("mode", "NORMAL")) != "NORMAL")
        if non_normal >= len(hist) * 0.45:
            points += 2
            signals.append("persistent_degradation_modes")

    rel = reliability or {}
    if (rel.get("runtime_fatigue") or {}).get("runtime_fatigue_band") in ("MODERATE", "HIGH"):
        points += 1
        signals.append("runtime_fatigue_elevated")

    audits = st.get("weekly_audits") or {}
    if len(audits) >= 3:
        mats = [float((audits[k] or {}).get("vitality_score") or 0.5) for k in sorted(audits.keys())[-3:]]
        if max(mats) - min(mats) < 0.03 and mats[-1] < 0.5:
            points += 1
            signals.append("maturity_stagnation_low_vitality")

    sw = (slimming or {}).get("state_weight") or {}
    if float(sw.get("adaptive_state_weight") or 0) >= 0.55:
        points += 1
        signals.append("state_weight_rebound")

    deg = str((degradation or {}).get("mode", "NORMAL"))
    if deg != "NORMAL" and len(hist) >= 4:
        points += 1
        signals.append("degradation_persistence")

    band = "HEALTHY"
    if points >= 3:
        band = "DEGRADED"
    elif points >= 1:
        band = "WATCH"

    return {
        "uptime_stability_health": band,
        "stability_signals": signals,
        "instability_points": points,
    }
