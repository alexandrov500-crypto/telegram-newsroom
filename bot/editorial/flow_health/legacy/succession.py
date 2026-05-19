from __future__ import annotations

from typing import Any


def evaluate_succession_readiness(
    *,
    governance: dict[str, Any] | None = None,
    dependency: dict[str, Any] | None = None,
    legibility: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Another operator could inherit stewardship without destabilizing — advisory."""
    gov = governance or {}
    dep = dependency or {}
    leg = legibility or {}
    clos = gov.get("closure") or {}
    doc = gov.get("doctrine") or {}
    min_g = gov.get("minimalism") or {}
    omem = gov.get("operational_memory") or {}
    sres = gov.get("strategic_resilience") or {}

    closure_ok = bool(
        clos.get("operational_closure_candidate")
        or (
            clos.get("architectural_sufficiency")
            and int(clos.get("steady_state_streak_days") or 0) >= 7
        ),
    )
    ready = bool(
        closure_ok
        and doc.get("stewardship_constitution_band") in ("CONSTITUTIONAL", "ALIGNED")
        and dep.get("stewardship_dependency_risk") == "LOW"
        and leg.get("operational_legibility_band") in ("LEGIBLE", "INSTITUTIONAL")
        and (omem.get("recovery_pattern") or {}).get("recovery_quality_improving", True)
        and not (omem.get("recovery_pattern") or {}).get("interventions_likely_hurting")
        and int(min_g.get("quiet_infrastructure_streak_days") or 0) >= 7
        and float(min_g.get("operational_entropy_accumulation") or 1) < 0.3
        and sres.get("long_horizon_sustainability")
    )

    return {"succession_readiness": ready}
