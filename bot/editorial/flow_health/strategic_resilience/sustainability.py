from __future__ import annotations

from typing import Any


def assess_sustainability_dimensions(
    *,
    governance: dict[str, Any] | None = None,
    certification: dict[str, Any] | None = None,
    freeze_registry: dict[str, Any] | None = None,
    operational_memory: dict[str, Any] | None = None,
    doctrine: dict[str, Any] | None = None,
    reliability: dict[str, Any] | None = None,
    ctx: dict[str, Any] | None = None,
    editorial_identity: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Long-horizon sustainability heuristics — not current health snapshot."""
    gov = governance or {}
    cert = certification or {}
    frz = freeze_registry or {}
    omem = operational_memory or {}
    doc = doctrine or {}
    rel = reliability or {}
    ctx = ctx or {}
    edit = editorial_identity or {}

    vitality = float(
        edit.get("editorial_vitality_score")
        or (gov.get("vitality") or {}).get("vitality", {}).get("editorial_vitality_score")
        or 0.55,
    )
    realism = float(
        edit.get("operational_realism_index")
        or (gov.get("vitality") or {}).get("realism", {}).get("operational_realism_index")
        or 0.65,
    )

    operational = 0.7
    if (frz.get("drift_exposure") or {}).get("drift_exposure_band") == "MINIMAL":
        operational += 0.15
    if (cert.get("operational_confidence") or {}).get("operational_confidence_band") == "CERTIFIED":
        operational += 0.1
    rehe = gov.get("rehearsal") or {}
    if (rehe.get("uptime_stability") or {}).get("uptime_stability_health") == "HEALTHY":
        operational += 0.05
    operational = min(1.0, operational)

    editorial = min(1.0, vitality * 0.5 + realism * 0.5)
    if omem.get("institutional_calmness_band") in ("MATURE", "INSTITUTIONAL"):
        editorial = min(1.0, editorial + 0.08)

    chg = (cert.get("change_pressure") or {}).get("change_pressure_band", "LOW")
    intervention = 0.75 if chg == "LOW" else 0.45 if chg == "ELEVATED" else 0.25
    if not omem.get("recurrence_detected"):
        intervention += 0.1
    intervention = min(1.0, intervention)

    bounded = bool((doc.get("complexity_continuity") or {}).get("complexity_bounded"))
    complexity = 0.7 if bounded else 0.45
    if doc.get("doctrine_alignment_status") == "ALIGNED":
        complexity = min(1.0, complexity + 0.15)

    cadence_h = float((ctx.get("flow_cadence") or {}).get("cadence_health") or 0.5)
    cadence = min(1.0, cadence_h + (0.1 if str((gov.get("degradation") or {}).get("mode")) == "NORMAL" else 0))

    dims = {
        "operational_sustainability": round(operational, 3),
        "editorial_sustainability": round(editorial, 3),
        "intervention_sustainability": round(intervention, 3),
        "complexity_sustainability": round(complexity, 3),
        "cadence_sustainability": round(cadence, 3),
    }
    aggregate = round(sum(dims.values()) / len(dims), 3)
    return {"dimensions": dims, "sustainability_aggregate": aggregate}
