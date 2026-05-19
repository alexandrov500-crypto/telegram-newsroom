from __future__ import annotations

from typing import Any


def assess_governance_converged(
    *,
    governance: dict[str, Any] | None = None,
    novelty: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Governance understanding stabilized — not frozen architecture."""
    gov = governance or {}
    novelty = novelty or {}
    obs = gov.get("observability") or {}
    clos = gov.get("closure") or {}
    leg = gov.get("legacy") or {}
    doc = gov.get("doctrine") or {}
    min_g = gov.get("minimalism") or {}
    cert = gov.get("certification") or {}

    obs_stable = (
        obs.get("governance_cohesion_status") in ("COHERENT", "CANONICAL")
        and obs.get("observability_integrity_band") in ("STABLE", "CANONICAL")
        and not obs.get("observability_drift_detected")
    )
    closure_stable = bool(
        clos.get("operational_closure_candidate") or clos.get("architectural_sufficiency"),
    )
    transfer_stable = leg.get("institutional_transferability_band") in (
        "TRANSFERABLE",
        "INSTITUTIONALIZED",
    ) or bool(leg.get("succession_readiness"))
    doctrine_stable = bool(doc.get("institutional_stewardship_mode")) and not doc.get(
        "doctrine_drift_detected",
    )
    minimalism_stable = bool(min_g.get("invisible_digest_mode")) or not min_g.get(
        "operational_entropy_accumulation",
        1,
    ) >= 0.35
    low_entropy = not (min_g.get("entropy") or {}).get("entropy_elevated", False)
    if min_g.get("operational_entropy_accumulation", 1) < 0.35:
        low_entropy = True
    low_expansion = not clos.get("expansion_pressure_detected")
    low_novelty = float(novelty.get("stewardship_novelty_decay") or 0) >= 0.65

    calm_reaffirm = (
        (cert.get("operational_confidence") or {}).get("operational_confidence_band")
        in ("TRUSTED", "CERTIFIED", None)
        and (gov.get("rehearsal") or {}).get("uptime_stability", {}).get(
            "uptime_stability_health",
        )
        in ("HEALTHY", None)
    )

    checks = [
        obs_stable,
        closure_stable,
        transfer_stable,
        doctrine_stable,
        minimalism_stable,
        low_entropy,
        low_expansion,
        low_novelty,
        calm_reaffirm,
    ]
    converged = sum(checks) >= 7

    return {
        "governance_converged": converged,
        "convergence_checks_passed": sum(checks),
        "convergence_checks_total": len(checks),
    }
