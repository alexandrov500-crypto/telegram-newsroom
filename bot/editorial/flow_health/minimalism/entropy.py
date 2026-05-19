from __future__ import annotations

from typing import Any

from bot.editorial.flow_health.minimalism.redundancy import detect_governance_redundancy


def measure_operational_entropy(
    *,
    governance: dict[str, Any] | None = None,
    redundancy: dict[str, Any] | None = None,
    cockpit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Architectural sediment — interpretive noise, not instability."""
    gov = governance or {}
    red = redundancy or detect_governance_redundancy(governance=gov, cockpit=cockpit)
    cockpit = cockpit or {}

    signals: list[str] = []
    points = 0.0

    points += min(0.25, int(red.get("redundancy_count") or 0) * 0.04)
    if int((red.get("overlap") or {}).get("governance_overlap_count") or 0) >= 2:
        points += 0.15
        signals.append("multiple_layers_describe_same_condition")

    subsystems = sum(
        1
        for k in (
            "rehearsal",
            "certification",
            "freeze_registry",
            "operational_memory",
            "doctrine",
            "strategic_resilience",
        )
        if gov.get(k)
    )
    if subsystems >= 6 and float(cockpit.get("warning_pressure") or 0) < 0.25:
        points += 0.12
        signals.append("many_calm_only_advisory_subsystems")

    if len(cockpit.get("active_warnings") or []) <= 1 and len(cockpit.get("cockpit_bullets") or []) >= 5:
        points += 0.1
        signals.append("excessive_stewardship_commentary")

    rel = gov.get("reliability") or {}
    if float((rel.get("telemetry_density") or {}).get("telemetry_density_score") or 0) >= 0.55:
        points += 0.1
        signals.append("telemetry_interpretive_residue")

    st_entries = len((gov.get("strategic_resilience") or {}).get("strategic_resilience_memory", {}).get("entries") or [])
    if st_entries >= 20:
        points += 0.08
        signals.append("stale_memory_structures_accumulating")

    accumulation = round(min(1.0, points), 3)
    return {
        "operational_entropy_accumulation": accumulation,
        "entropy_signals": signals[:6],
        "entropy_elevated": accumulation >= 0.35,
    }
