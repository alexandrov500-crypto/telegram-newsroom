from __future__ import annotations

from typing import Any


def assess_institutional_transferability(
    *,
    dependency: dict[str, Any] | None = None,
    legibility: dict[str, Any] | None = None,
    succession: dict[str, Any] | None = None,
    governance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Is maturity a property of the system or of one steward?"""
    dep = dependency or {}
    leg = legibility or {}
    succ = succession or {}
    gov = governance or {}
    omem = gov.get("operational_memory") or {}

    band = "PERSON_DEPENDENT"
    if succ.get("succession_readiness") and leg.get("operational_legibility_band") == "INSTITUTIONAL":
        band = "INSTITUTIONALIZED"
    elif leg.get("operational_legibility_band") in ("LEGIBLE", "INSTITUTIONAL") and dep.get(
        "stewardship_dependency_risk",
    ) == "LOW":
        band = "TRANSFERABLE"
    elif dep.get("stewardship_dependency_risk") == "MODERATE":
        band = "TRANSITIONAL"
    elif omem.get("institutional_calmness_band") in ("MATURE", "INSTITUTIONAL") and dep.get(
        "stewardship_dependency_risk",
    ) != "HIGH":
        band = "TRANSITIONAL"

    return {"institutional_transferability_band": band}
