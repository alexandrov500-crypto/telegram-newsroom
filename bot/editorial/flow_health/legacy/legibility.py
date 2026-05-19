from __future__ import annotations

from typing import Any


def compute_operational_legibility(
    *,
    governance: dict[str, Any] | None = None,
    dependency: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Operational comprehensibility without tribal knowledge."""
    gov = governance or {}
    dep = dependency or {}
    doc = gov.get("doctrine") or {}
    min_g = gov.get("minimalism") or {}
    clos = gov.get("closure") or {}
    omem = gov.get("operational_memory") or {}
    rehe = gov.get("rehearsal") or {}

    raw = 0.55
    if doc.get("doctrine_alignment_status") == "ALIGNED":
        raw += 0.12
    if doc.get("institutional_stewardship_mode"):
        raw += 0.08
    if min_g.get("architectural_compression_band") in ("COMPRESSED", "MINIMALIST"):
        raw += 0.08
    if clos.get("architectural_sufficiency"):
        raw += 0.1
    if (rehe.get("recovery_calmness") or {}).get("recovery_calmness_band") == "CALM":
        raw += 0.06
    if not omem.get("recurrence_detected"):
        raw += 0.05
    if dep.get("stewardship_dependency_risk") == "LOW":
        raw += 0.1
    elif dep.get("stewardship_dependency_risk") == "HIGH":
        raw -= 0.2

    index = round(max(0.0, min(1.0, raw)), 3)
    band = "OPAQUE"
    if index >= 0.78:
        band = "INSTITUTIONAL"
    elif index >= 0.62:
        band = "LEGIBLE"
    elif index >= 0.42:
        band = "PARTIAL"

    return {
        "operational_legibility_index": index,
        "operational_legibility_band": band,
    }
