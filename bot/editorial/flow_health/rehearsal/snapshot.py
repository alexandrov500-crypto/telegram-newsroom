from __future__ import annotations

from typing import Any

from bot.editorial.flow_health.rehearsal.core_freeze import validate_core_freeze_candidate
from bot.editorial.flow_health.rehearsal.drift_boundaries import analyze_drift_boundaries
from bot.editorial.flow_health.rehearsal.maintenance_readiness import assess_maintenance_readiness
from bot.editorial.flow_health.rehearsal.operational_load import assess_operational_load
from bot.editorial.flow_health.rehearsal.profiles import infer_active_rehearsal_profile
from bot.editorial.flow_health.rehearsal.recovery_calmness import compute_recovery_calmness
from bot.editorial.flow_health.rehearsal.uptime_stability import validate_uptime_stability


def rehearsal_snapshot(
    *,
    ctx: dict[str, Any] | None = None,
    reliability: dict[str, Any] | None = None,
    slimming: dict[str, Any] | None = None,
    governance: dict[str, Any] | None = None,
    cockpit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Production survivability rehearsal — advisory verification bundle."""
    gov = governance or (ctx or {}).get("flow_governance") or {}
    rel = reliability or gov.get("reliability") or {}
    slim = slimming or gov.get("slimming") or {}

    profile = infer_active_rehearsal_profile(ctx or {"flow_governance": gov})
    uptime = validate_uptime_stability(
        reliability=rel,
        slimming=slim,
        degradation=gov.get("degradation"),
    )
    drift = analyze_drift_boundaries(baseline=gov.get("baseline"), reliability=rel)
    calmness = compute_recovery_calmness(
        recovery_envelope=rel.get("recovery_envelope"),
        degradation=gov.get("degradation"),
    )
    load = assess_operational_load(
        influences=(gov.get("durability") or {}).get("influences"),
        reliability=rel,
        cockpit=cockpit,
        adaptive=(ctx or {}).get("flow_adaptive"),
    )
    core_health = slim.get("core_health") or {}
    maintenance = assess_maintenance_readiness(
        reliability=rel,
        slimming=slim,
        core_health=core_health,
        simplicity=(gov.get("durability") or {}).get("simplicity"),
    )
    freeze = validate_core_freeze_candidate(
        ctx=ctx,
        reliability=rel,
        maintenance=maintenance,
        uptime=uptime,
    )

    executive_lines: list[str] = []
    if uptime["uptime_stability_health"] != "HEALTHY":
        executive_lines.append(f"Uptime stability: {uptime['uptime_stability_health']}")
    if drift["drift_boundary_status"] != "WITHIN_BOUNDS":
        executive_lines.append(f"Drift boundaries: {drift['drift_boundary_status']}")
    if calmness["recovery_calmness_band"] != "CALM":
        executive_lines.append(f"Recovery calmness: {calmness['recovery_calmness_band']}")
    if load["operational_load_band"] != "LIGHT":
        executive_lines.append(f"Operational load: {load['operational_load_band']}")
    if maintenance["maintenance_readiness"] != "READY":
        executive_lines.append(f"Maintenance: {maintenance['maintenance_readiness']}")
    if freeze["core_freeze_candidate"]:
        executive_lines.append("Core freeze candidate: ready for long-duration ops mode")
    elif freeze.get("blockers"):
        executive_lines.append(f"Core freeze blocked: {', '.join(freeze['blockers'][:2])}")
    executive_lines.append(f"Profile: {profile['active_profile']}")

    return {
        "rehearsal_profile": profile,
        "uptime_stability": uptime,
        "drift_boundaries": drift,
        "recovery_calmness": calmness,
        "operational_load": load,
        "maintenance_readiness": maintenance,
        "core_freeze": freeze,
        "executive_summary_lines": executive_lines[:8],
    }
