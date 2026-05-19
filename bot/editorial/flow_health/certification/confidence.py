from __future__ import annotations

from typing import Any


def compute_operational_confidence(
    *,
    reliability: dict[str, Any] | None = None,
    rehearsal: dict[str, Any] | None = None,
    evidence: dict[str, Any] | None = None,
    change_pressure: dict[str, Any] | None = None,
    stabilization: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Long-run unattended operation confidence — advisory."""
    rel = reliability or {}
    rehe = rehearsal or {}
    ev = evidence or {}
    chg = change_pressure or {}
    stab = stabilization or {}

    mat = float((rel.get("operational_maturity") or {}).get("operational_maturity_index") or 0.65)
    surv = float((rel.get("survivability") or {}).get("survivability_score") or 0.7)
    calm = float((rehe.get("recovery_calmness") or {}).get("recovery_calmness_score") or 0.75)
    fatigue = float((rel.get("runtime_fatigue") or {}).get("runtime_fatigue_score") or 0.2)
    drift_ok = (rehe.get("drift_boundaries") or {}).get("drift_boundary_status") == "WITHIN_BOUNDS"
    freeze_ok = stab.get("stabilization_freeze_status") == "STABLE_FREEZE"
    evidence_n = len(ev.get("operational_evidence_summary") or [])
    load_light = (rehe.get("operational_load") or {}).get("operational_load_band") == "LIGHT"

    raw = (
        mat * 0.22
        + surv * 0.2
        + calm * 0.18
        + (1 - fatigue) * 0.12
        + (0.08 if drift_ok else 0)
        + (0.08 if freeze_ok else 0)
        + min(0.12, evidence_n * 0.025)
        + (0.05 if load_light else 0)
    )
    if chg.get("change_pressure_band") == "DESTABILIZING":
        raw -= 0.2
    elif chg.get("change_pressure_band") == "ELEVATED":
        raw -= 0.08

    index = round(max(0.0, min(1.0, raw)), 3)
    band = "PROVISIONAL"
    if index >= 0.78 and freeze_ok and drift_ok and chg.get("change_pressure_band") == "LOW":
        band = "CERTIFIED"
    elif index >= 0.62:
        band = "TRUSTED"

    return {
        "operational_confidence_index": index,
        "operational_confidence_band": band,
    }
