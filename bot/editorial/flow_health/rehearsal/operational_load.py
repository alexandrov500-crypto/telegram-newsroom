from __future__ import annotations

from typing import Any


def assess_operational_load(
    *,
    influences: dict[str, Any] | None = None,
    reliability: dict[str, Any] | None = None,
    cockpit: dict[str, Any] | None = None,
    adaptive: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Operational creep proxy — advisory load band."""
    infl_count = int((influences or {}).get("influence_count") or 0)
    warnings = len((cockpit or {}).get("active_warnings") or [])
    bullets = len((cockpit or {}).get("cockpit_bullets") or [])
    scale = float((adaptive or {}).get("relaxation", {}).get("effective_scale") or 0)
    density = float((reliability or {}).get("telemetry_density", {}).get("telemetry_density_score") or 0)

    load_points = infl_count + warnings + int(bullets > 6) + int(scale > 0.35) + int(density > 0.6)
    band = "LIGHT"
    if load_points >= 8:
        band = "HEAVY"
    elif load_points >= 4:
        band = "MODERATE"

    return {
        "operational_load_band": band,
        "load_points": load_points,
        "advisory_density": infl_count + warnings,
    }
