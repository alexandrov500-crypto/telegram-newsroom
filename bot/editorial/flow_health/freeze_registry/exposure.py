from __future__ import annotations

from typing import Any

from bot.editorial.flow_health.freeze_registry.drift import evolution_volatility_score


def compute_drift_exposure_index(
    *,
    registry: dict[str, Any] | None = None,
    certification: dict[str, Any] | None = None,
    rehearsal: dict[str, Any] | None = None,
    governance: dict[str, Any] | None = None,
    cockpit: dict[str, Any] | None = None,
    evolution_ledger: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    Operational fragility from intervention — distinct from reliability.
    drift_exposure_index 0..1, band MINIMAL|CONTROLLED|ELEVATED|FRAGILE.
    """
    reg = registry or {}
    cert = certification or {}
    rehe = rehearsal or {}
    cockpit = cockpit or {}

    experimental = float(reg.get("experimental_surface_ratio") or 0)
    chg = cert.get("change_pressure") or {}
    chg_score = float(chg.get("change_pressure_score") or 0)
    warnings = len(cockpit.get("active_warnings") or [])
    warn_density = min(1.0, warnings / 8.0)

    stab = cert.get("stabilization_freeze") or {}
    violations = len(stab.get("freeze_violations") or [])
    viol_score = min(1.0, violations * 0.35)

    drift_status = (rehe.get("drift_boundaries") or {}).get("drift_boundary_status", "WITHIN_BOUNDS")
    drift_score = 0.0
    if drift_status == "ELEVATED":
        drift_score = 0.35
    elif drift_status == "BREACH":
        drift_score = 0.65

    evo_vol = evolution_volatility_score(evolution_ledger or {})

    raw = (
        experimental * 0.15
        + chg_score * 0.25
        + warn_density * 0.15
        + viol_score * 0.2
        + drift_score * 0.15
        + evo_vol * 0.1
    )
    index = round(max(0.0, min(1.0, raw)), 3)

    band = "MINIMAL"
    if index >= 0.62:
        band = "FRAGILE"
    elif index >= 0.38:
        band = "ELEVATED"
    elif index >= 0.18:
        band = "CONTROLLED"

    return {
        "drift_exposure_index": index,
        "drift_exposure_band": band,
        "components": {
            "experimental_surface_ratio": experimental,
            "change_pressure_score": chg_score,
            "warning_density": round(warn_density, 3),
            "freeze_violations": violations,
            "operational_drift_score": drift_score,
            "evolution_volatility": evo_vol,
        },
    }


def estimate_stewardship_horizon(
    *,
    certification: dict[str, Any] | None = None,
    rehearsal: dict[str, Any] | None = None,
    reliability: dict[str, Any] | None = None,
    drift_exposure: dict[str, Any] | None = None,
    cockpit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Heuristic days without engineering intervention — advisory only."""
    cert = certification or {}
    rehe = rehearsal or {}
    rel = reliability or {}
    exp = drift_exposure or {}
    cockpit = cockpit or {}

    conf = float((cert.get("operational_confidence") or {}).get("operational_confidence_index") or 0.6)
    chg_band = (cert.get("change_pressure") or {}).get("change_pressure_band", "LOW")
    freeze_ok = (cert.get("stabilization_freeze") or {}).get("stabilization_freeze_status") == "STABLE_FREEZE"
    calm = (rehe.get("recovery_calmness") or {}).get("recovery_calmness_band") == "CALM"
    surv = float((rel.get("survivability") or {}).get("survivability_score") or 0.7)
    warn_p = float(cockpit.get("warning_pressure") or 0)
    exposure = float(exp.get("drift_exposure_index") or 0.3)

    days = int(
        conf * 21
        + surv * 14
        + (10 if freeze_ok else 0)
        + (7 if calm else 0)
        + (5 if chg_band == "LOW" else 0)
        - exposure * 18
        - warn_p * 12
    )
    days = max(1, min(90, days))

    band = "SHORT"
    if days >= 45 and conf >= 0.78 and chg_band == "LOW" and exposure < 0.2:
        band = "AUTONOMOUS_CANDIDATE"
    elif days >= 28:
        band = "LONG"
    elif days >= 14:
        band = "STABLE"

    return {
        "stewardship_horizon_days": days,
        "stewardship_horizon_band": band,
    }
