from __future__ import annotations

from typing import Any


def assess_stewardship_dependency_risk(
    *,
    governance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Maturity not yet institutionally transferable — not operator evaluation."""
    gov = governance or {}
    cert = gov.get("certification") or {}
    omem = gov.get("operational_memory") or {}
    rel = gov.get("reliability") or {}
    sres = gov.get("strategic_resilience") or {}
    doc = gov.get("doctrine") or {}

    signals: list[str] = []
    points = 0

    chg = (cert.get("change_pressure") or {}).get("change_pressure_band", "LOW")
    if chg in ("ELEVATED", "DESTABILIZING"):
        points += 2
        signals.append("recurring_manual_intervention")

    if (omem.get("recovery_pattern") or {}).get("interventions_likely_hurting"):
        points += 1
        signals.append("non_transferable_stabilization_patterns")

    if omem.get("recurrence_detected"):
        points += 1
        signals.append("repeated_intervention_cycles")

    absence = (rel.get("operator_absence") or {}).get("operator_absence_level")
    if absence in ("MILD_ABSENCE", "EXTENDED_ABSENCE"):
        points += 1
        signals.append("calmness_sensitive_to_operator_presence")

    if (sres.get("stewardship_fatigue") or {}).get("stewardship_fatigue_detected"):
        points += 1
        signals.append("stewardship_fatigue_from_tuning")

    if doc.get("doctrine_alignment_status") not in ("ALIGNED",) and doc.get(
        "stewardship_constitution_band",
    ) not in ("CONSTITUTIONAL", "ALIGNED"):
        points += 1
        signals.append("governance_without_explicit_doctrine_continuity")

    freeze = (rel.get("freeze_discipline") or {}).get("freeze_discipline_status")
    if freeze == "HIGH_TUNING_CHURN":
        points += 2
        signals.append("high_tuning_dependence")

    risk = "LOW"
    if points >= 4:
        risk = "HIGH"
    elif points >= 2:
        risk = "MODERATE"

    return {
        "stewardship_dependency_risk": risk,
        "dependency_risk_points": points,
        "dependency_signals": signals[:6],
    }
