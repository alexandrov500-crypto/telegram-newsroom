from __future__ import annotations

from typing import Any


def compute_governance_finalization(
    *,
    converged: dict[str, Any] | None = None,
    recursion: dict[str, Any] | None = None,
    novelty: dict[str, Any] | None = None,
    continuity: dict[str, Any] | None = None,
    governance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Explanatory completeness — not project complete or stop development."""
    converged = converged or {}
    recursion = recursion or {}
    novelty = novelty or {}
    continuity = continuity or {}
    gov = governance or {}

    raw = 0.4
    if converged.get("governance_converged"):
        raw += 0.22
    if not recursion.get("stewardship_recursion_detected"):
        raw += 0.12

    obs = gov.get("observability") or {}
    if obs.get("governance_cohesion_status") in ("COHERENT", "CANONICAL"):
        raw += 0.08
    if obs.get("observability_integrity_band") in ("STABLE", "CANONICAL"):
        raw += 0.06

    streak = int(continuity.get("governance_convergence_streak_days") or 0)
    if streak >= 14:
        raw += 0.12
    elif streak >= 7:
        raw += 0.06

    decay = float(novelty.get("stewardship_novelty_decay") or 0)
    raw += decay * 0.15

    clos = gov.get("closure") or {}
    if clos.get("operational_closure_candidate"):
        raw += 0.05

    leg = gov.get("legacy") or {}
    if leg.get("institutional_transferability_band") in ("TRANSFERABLE", "INSTITUTIONALIZED"):
        raw += 0.05

    if recursion.get("stewardship_recursion_detected"):
        raw -= 0.18

    index = round(max(0.0, min(1.0, raw)), 3)
    band = "FORMING"
    if index >= 0.85 and converged.get("governance_converged") and streak >= 14:
        band = "FINALIZED"
    elif index >= 0.72 and converged.get("governance_converged"):
        band = "CONVERGED"
    elif index >= 0.5:
        band = "EVOLVED"

    return {
        "governance_finalization_index": index,
        "governance_finalization_band": band,
    }


def evaluate_governance_finalization_candidate(
    *,
    converged: dict[str, Any] | None = None,
    recursion: dict[str, Any] | None = None,
    novelty: dict[str, Any] | None = None,
    continuity: dict[str, Any] | None = None,
    finalization: dict[str, Any] | None = None,
    governance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    gov = governance or {}
    obs = gov.get("observability") or {}
    clos = gov.get("closure") or {}
    min_g = gov.get("minimalism") or {}
    leg = gov.get("legacy") or {}
    streak = int(continuity.get("governance_convergence_streak_days") or 0)

    candidate = bool(
        converged.get("governance_converged")
        and not recursion.get("stewardship_recursion_detected")
        and clos.get("operational_closure_candidate")
        and obs.get("canonical_observability_quiet")
        and (
            leg.get("institutional_transferability_band") in ("TRANSFERABLE", "INSTITUTIONALIZED")
            or leg.get("succession_readiness")
        )
        and not (min_g.get("entropy") or {}).get("entropy_elevated", True)
        and not clos.get("expansion_pressure_detected")
        and streak >= 14
        and float(novelty.get("stewardship_novelty_decay") or 0) >= 0.7
        and finalization.get("governance_finalization_band") in ("CONVERGED", "FINALIZED")
    )

    return {"governance_finalization_candidate": candidate}
