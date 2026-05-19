from __future__ import annotations

from typing import Any

from bot.editorial.flow_health.slimming.change_risk import analyze_change_risk
from bot.editorial.flow_health.slimming.config_surface import analyze_config_surface
from bot.editorial.flow_health.slimming.consolidation import analyze_heuristic_consolidation
from bot.editorial.flow_health.slimming.operational_core import assess_core_health, operational_core_map
from bot.editorial.flow_health.slimming.profile_hardening import minimal_durable_profile
from bot.editorial.flow_health.slimming.state_weight import minimize_adaptive_state


def slimming_snapshot(
    *,
    ctx: dict[str, Any] | None = None,
    adaptive: dict[str, Any] | None = None,
    influences: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Runtime slimming advisory bundle — no publish behavior changes."""
    consolidation = analyze_heuristic_consolidation(
        influences=influences,
        adaptive=adaptive,
    )
    config_surface = analyze_config_surface()
    state_weight = minimize_adaptive_state()
    change_risk = analyze_change_risk(
        influence_count=int(consolidation.get("heuristic_density") or 0),
    )
    core_map = operational_core_map()
    profile = minimal_durable_profile()
    core_health = assess_core_health(ctx or {}) if ctx else {}

    return {
        "consolidation": consolidation,
        "config_surface": config_surface,
        "state_weight": state_weight,
        "change_risk": change_risk,
        "operational_core": core_map,
        "core_health": core_health,
        "profile": profile,
    }
