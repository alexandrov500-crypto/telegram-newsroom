from __future__ import annotations

from typing import Any


def validate_operational_certification_candidate(
    *,
    ctx: dict[str, Any] | None = None,
    rehearsal: dict[str, Any] | None = None,
    reliability: dict[str, Any] | None = None,
    confidence: dict[str, Any] | None = None,
    change_pressure: dict[str, Any] | None = None,
    maintenance_mode: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Advisory certification candidacy — extends frozen-core validation."""
    rehe = rehearsal or {}
    rel = reliability or {}
    conf = confidence or {}
    chg = change_pressure or {}
    mm = maintenance_mode or {}

    core = rehe.get("core_freeze") or {}
    drift = (rehe.get("drift_boundaries") or {}).get("drift_boundary_status") == "WITHIN_BOUNDS"
    calm = (rehe.get("recovery_calmness") or {}).get("recovery_calmness_band") == "CALM"
    fatigue_low = (rel.get("runtime_fatigue") or {}).get("runtime_fatigue_band") in (None, "LOW")
    mat_band = (rel.get("operational_maturity") or {}).get("operational_maturity_band") in (
        "STABLE",
        "MATURE",
    )
    flow = (ctx or {}).get("publish_funnel") or {}
    low_dup_pressure = not bool((flow.get("duplicate_pressure") or {}).get("elevated"))

    candidate = (
        bool(core.get("core_freeze_candidate"))
        and mm.get("maintenance_mode_ready")
        and conf.get("operational_confidence_band") == "CERTIFIED"
        and chg.get("change_pressure_band") == "LOW"
        and drift
        and calm
        and fatigue_low
        and mat_band
        and low_dup_pressure
    )

    blockers = list(core.get("blockers") or [])
    if not mm.get("maintenance_mode_ready"):
        blockers.append("maintenance_mode_not_ready")
    if conf.get("operational_confidence_band") != "CERTIFIED":
        blockers.append("confidence_not_certified")
    if chg.get("change_pressure_band") != "LOW":
        blockers.append("change_pressure_elevated")
    if not drift:
        blockers.append("drift_boundaries")
    if not calm:
        blockers.append("recovery_not_calm")

    return {
        "operational_certification_candidate": candidate,
        "certification_blockers": list(dict.fromkeys(blockers))[:8],
    }
