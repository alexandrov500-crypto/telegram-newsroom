from __future__ import annotations

import os
from typing import Any


def measure_telemetry_density(
    *,
    cockpit: dict[str, Any] | None = None,
    ctx: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Cockpit density metric — higher means noisier digest; triggers stronger pruning.
    """
    cockpit = cockpit or {}
    bullets = cockpit.get("cockpit_bullets") or []
    warnings = cockpit.get("active_warnings") or []
    gov = (ctx or {}).get("flow_governance") or {}

    line_count = len(bullets) + len(warnings)
    if gov.get("slimming"):
        line_count += 2
    if (gov.get("vitality") or {}).get("stagnation", {}).get("stagnation_risk") not in (
        None,
        "LOW",
    ):
        line_count += 1

    density = round(min(1.0, line_count / 12.0), 3)
    creep = density >= float(os.getenv("TELEMETRY_DENSITY_CREEP", "0.55"))
    strong_prune = density >= float(os.getenv("TELEMETRY_DENSITY_STRONG_PRUNE", "0.7"))

    return {
        "telemetry_density_score": density,
        "cockpit_line_estimate": line_count,
        "telemetry_creep_detected": creep,
        "strong_pruning_recommended": strong_prune,
        "collapse_protection_active": os.getenv(
            "TELEMETRY_COLLAPSE_PROTECTION",
            "true",
        ).lower()
        in ("1", "true", "yes", "on"),
    }


def apply_collapse_protection(
    bullets: list[str],
    density: dict[str, Any],
) -> list[str]:
    """Tighter cap when density rises — prevents telemetry re-expansion."""
    if not density.get("collapse_protection_active"):
        return bullets
    max_lines = 5
    if density.get("strong_pruning_recommended"):
        max_lines = 3
    elif density.get("telemetry_creep_detected"):
        max_lines = 4
    return bullets[:max_lines]
