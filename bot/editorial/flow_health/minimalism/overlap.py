from __future__ import annotations

from typing import Any


def detect_governance_overlap(
    *,
    governance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Overlapping advisory dimensions across maturity layers."""
    gov = governance or {}
    overlaps: list[str] = []

    rehe = gov.get("rehearsal") or {}
    doc = gov.get("doctrine") or {}
    frz = gov.get("freeze_registry") or {}
    sres = gov.get("strategic_resilience") or {}
    omem = gov.get("operational_memory") or {}
    cert = gov.get("certification") or {}

    drift_layers = 0
    if (rehe.get("drift_boundaries") or {}).get("drift_boundary_status") not in (None, "WITHIN_BOUNDS"):
        drift_layers += 1
    if (frz.get("drift_exposure") or {}).get("drift_exposure_band") not in (None, "MINIMAL"):
        drift_layers += 1
    if doc.get("doctrine_drift_detected"):
        drift_layers += 1
    if (sres.get("erosion") or {}).get("architectural_erosion_detected"):
        drift_layers += 1
    if drift_layers >= 2:
        overlaps.append("drift_covered_by_doctrine_resilience_rehearsal")

    calm_layers = 0
    if omem.get("institutional_calmness_index") is not None:
        calm_layers += 1
    if doc.get("stewardship_constitution_score") is not None:
        calm_layers += 1
    if sres.get("strategic_resilience_index") is not None:
        calm_layers += 1
    if (cert.get("operational_confidence") or {}).get("operational_confidence_index") is not None:
        calm_layers += 1
    if calm_layers >= 3:
        overlaps.append("duplicated_calmness_maturity_metrics")

    if (rehe.get("recovery_calmness") and sres.get("strategic_resilience")):
        overlaps.append("recovery_quality_described_in_multiple_layers")

    if frz.get("stewardship_horizon") and sres.get("sustainability_horizon"):
        overlaps.append("horizon_metrics_overlap")

    return {
        "governance_overlap_count": len(overlaps),
        "overlap_signals": overlaps,
    }
