from __future__ import annotations

from typing import Any


def build_legacy_digest_lines(
    *,
    succession: dict[str, Any] | None = None,
    legibility: dict[str, Any] | None = None,
    dependency: dict[str, Any] | None = None,
    transferability: dict[str, Any] | None = None,
    closure_ready: bool = False,
) -> list[str]:
    """Extremely quiet — transferability and dependency only."""
    succ = succession or {}
    leg = legibility or {}
    dep = dependency or {}
    trans = transferability or {}

    if succ.get("succession_readiness") and closure_ready:
        return ["Operational stewardship appears institutionally transferable"]

    if leg.get("operational_legibility_band") in ("LEGIBLE", "INSTITUTIONAL") and not dep.get(
        "stewardship_dependency_risk",
    ) == "HIGH":
        if trans.get("institutional_transferability_band") == "TRANSFERABLE":
            return ["Governance continuity remains operationally legible"]

    if dep.get("stewardship_dependency_risk") == "HIGH":
        sig = (dep.get("dependency_signals") or ["dependency risk"])[0]
        return [f"Stewardship dependency: {sig.replace('_', ' ')}"]
    if dep.get("stewardship_dependency_risk") == "MODERATE":
        return ["Stewardship continuity improving — some intervention patterns remain"]

    return []
