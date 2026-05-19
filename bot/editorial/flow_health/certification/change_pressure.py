from __future__ import annotations

from typing import Any

from bot.editorial.flow_health.state import load_state


def measure_change_pressure(
    *,
    freeze_discipline: dict[str, Any] | None = None,
    config_pressure: dict[str, Any] | None = None,
    cockpit: dict[str, Any] | None = None,
    stabilization: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Detect operational over-management — advisory."""
    cfg = config_pressure or {}
    freeze = freeze_discipline or {}
    stab = stabilization or {}
    points = 0

    advanced = int(cfg.get("advanced_touched") or 0)
    if advanced >= 3:
        points += 2
    elif advanced >= 1:
        points += 1

    if freeze.get("freeze_discipline_status") == "HIGH_TUNING_CHURN":
        points += 3
    elif freeze.get("freeze_discipline_status") == "ACTIVE_TUNING":
        points += 1

    if stab.get("freeze_violations"):
        points += len(stab["freeze_violations"])

    warnings = len((cockpit or {}).get("active_warnings") or [])
    if warnings >= 5:
        points += 1

    st = load_state()
    hist = dict(st.get("warning_history") or {})
    if len(hist) >= 12:
        points += 1

    band = "LOW"
    if points >= 5:
        band = "DESTABILIZING"
    elif points >= 2:
        band = "ELEVATED"

    return {
        "change_pressure_score": round(min(1.0, points / 7.0), 3),
        "change_pressure_band": band,
        "change_pressure_points": points,
    }
