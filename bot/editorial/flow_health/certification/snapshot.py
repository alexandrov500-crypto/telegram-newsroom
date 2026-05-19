from __future__ import annotations

from typing import Any

from bot.editorial.flow_health.certification.candidate import validate_operational_certification_candidate
from bot.editorial.flow_health.certification.change_pressure import measure_change_pressure
from bot.editorial.flow_health.certification.confidence import compute_operational_confidence
from bot.editorial.flow_health.certification.evidence import build_operational_evidence_summary
from bot.editorial.flow_health.certification.freeze_governance import assess_stabilization_freeze
from bot.editorial.flow_health.certification.lockdown import analyze_configuration_lockdown
from bot.editorial.flow_health.certification.maintenance_mode import validate_maintenance_mode_readiness


def certification_snapshot(
    *,
    ctx: dict[str, Any] | None = None,
    governance: dict[str, Any] | None = None,
    reliability: dict[str, Any] | None = None,
    rehearsal: dict[str, Any] | None = None,
    slimming: dict[str, Any] | None = None,
    cockpit: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Operational certification & stabilization freeze — advisory bundle."""
    gov = governance or (ctx or {}).get("flow_governance") or {}
    rel = reliability or gov.get("reliability") or {}
    rehe = rehearsal or gov.get("rehearsal") or {}
    slim = slimming or gov.get("slimming") or {}
    cockpit = cockpit or (gov.get("cockpit") if isinstance(gov.get("cockpit"), dict) else None)

    stabilization = assess_stabilization_freeze(
        config_pressure=gov.get("config_pressure"),
        freeze_discipline=rel.get("freeze_discipline"),
    )
    evidence = build_operational_evidence_summary(
        ctx=ctx,
        warning_pressure=float((cockpit or {}).get("warning_pressure") or 0),
        degradation_mode=str((gov.get("degradation") or {}).get("mode", "NORMAL")),
        calm_recovery=(rehe.get("recovery_calmness") or {}).get("recovery_calmness_band") == "CALM",
    )
    lockdown = analyze_configuration_lockdown(
        config_surface=slim.get("config_surface"),
    )
    change = measure_change_pressure(
        freeze_discipline=rel.get("freeze_discipline"),
        config_pressure=gov.get("config_pressure"),
        cockpit=cockpit,
        stabilization=stabilization,
    )
    confidence = compute_operational_confidence(
        reliability=rel,
        rehearsal=rehe,
        evidence=evidence,
        change_pressure=change,
        stabilization=stabilization,
    )
    maintenance = validate_maintenance_mode_readiness(
        rehearsal=rehe,
        stabilization=stabilization,
        change_pressure=change,
        confidence=confidence,
        reliability=rel,
    )
    certification = validate_operational_certification_candidate(
        ctx=ctx,
        rehearsal=rehe,
        reliability=rel,
        confidence=confidence,
        change_pressure=change,
        maintenance_mode=maintenance,
    )

    stewardship_lines: list[str] = []
    band = confidence.get("operational_confidence_band", "PROVISIONAL")
    if band != "CERTIFIED":
        stewardship_lines.append(
            f"Confidence {confidence.get('operational_confidence_index')} · {band}",
        )
    if stabilization.get("stabilization_freeze_status") != "STABLE_FREEZE":
        stewardship_lines.append(f"Freeze: {stabilization['stabilization_freeze_status']}")
    if change.get("change_pressure_band") != "LOW":
        stewardship_lines.append(f"Change pressure: {change['change_pressure_band']}")
    for ev in (evidence.get("operational_evidence_summary") or [])[:2]:
        stewardship_lines.append(ev)
    if maintenance.get("maintenance_mode_ready"):
        stewardship_lines.append("Maintenance-mode ready")
    elif maintenance.get("maintenance_mode_blockers"):
        stewardship_lines.append(
            f"Maintenance blocked: {', '.join(maintenance['maintenance_mode_blockers'][:2])}",
        )
    if certification.get("operational_certification_candidate"):
        stewardship_lines.append("Certification candidate: long-duration stable runtime")
    elif certification.get("certification_blockers"):
        stewardship_lines.append(
            f"Certification pending: {', '.join(certification['certification_blockers'][:2])}",
        )
    if lockdown.get("locked_surface_ratio", 0) >= 0.55 and change.get("change_pressure_band") == "LOW":
        stewardship_lines.append(
            f"Config lockdown surface {int(lockdown['locked_surface_ratio'] * 100)}% stable",
        )

    return {
        "stabilization_freeze": stabilization,
        "operational_evidence": evidence,
        "configuration_lockdown": lockdown,
        "change_pressure": change,
        "operational_confidence": confidence,
        "maintenance_mode": maintenance,
        "operational_certification": certification,
        "stewardship_summary_lines": stewardship_lines[:8],
    }
