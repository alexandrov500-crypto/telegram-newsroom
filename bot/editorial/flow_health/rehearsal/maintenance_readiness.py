from __future__ import annotations

from typing import Any


def assess_maintenance_readiness(
    *,
    reliability: dict[str, Any] | None = None,
    slimming: dict[str, Any] | None = None,
    core_health: dict[str, Any] | None = None,
    simplicity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """How safely maintainable is the newsroom now?"""
    rel = reliability or {}
    simp = simplicity or {}

    simplicity_score = float(
        simp.get("operational_simplicity_index")
        or (rel.get("operational_maturity") or {}).get("operational_maturity_index")
        or 0.65,
    )
    surv = float((rel.get("survivability") or {}).get("survivability_score") or 0.7)
    fatigue = float((rel.get("runtime_fatigue") or {}).get("runtime_fatigue_score") or 0.2)
    cfg = float((slimming or {}).get("config_surface", {}).get("configuration_pressure_score") or 0.2)
    core_ok = bool((core_health or {}).get("operational_core_healthy", True))
    churn = (rel.get("freeze_discipline") or {}).get("freeze_discipline_status") == "HIGH_TUNING_CHURN"

    raw = simplicity_score * 0.3 + surv * 0.25 + (1 - fatigue) * 0.2 + (1 - cfg) * 0.15 + (1.0 if core_ok else 0.4) * 0.1
    if churn:
        raw -= 0.15

    readiness = "READY"
    if raw < 0.5 or not core_ok or churn:
        readiness = "FRAGILE"
    elif raw < 0.68 or fatigue >= 0.45:
        readiness = "CAUTION"

    return {
        "maintenance_readiness": readiness,
        "readiness_score": round(max(0.0, min(1.0, raw)), 3),
        "freeze_appropriate": readiness == "READY" and not churn,
    }
