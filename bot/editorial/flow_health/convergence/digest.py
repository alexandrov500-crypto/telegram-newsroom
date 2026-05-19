from __future__ import annotations

from typing import Any


def build_convergence_digest_lines(
    *,
    converged: dict[str, Any] | None = None,
    recursion: dict[str, Any] | None = None,
    finalization: dict[str, Any] | None = None,
    candidate: dict[str, Any] | None = None,
    continuity: dict[str, Any] | None = None,
    finalization_quiet: bool = False,
) -> list[str]:
    """Max 1 line when finalization candidate — infrastructure silence."""
    if recursion.get("stewardship_recursion_detected"):
        sig = (recursion.get("recursion_signals") or ["recursive stewardship"])[0]
        if "digest" in sig or "layer" in sig:
            return ["Governance layering appears recursively self-descriptive"]
        return [f"Stewardship recursion: {sig.replace('_', ' ')[:72]}"]

    if finalization_quiet and candidate.get("governance_finalization_candidate"):
        streak = int(continuity.get("governance_convergence_streak_days") or 0)
        if streak >= 14:
            return ["Stewardship maturity remains explanatorily complete"]
        return ["Operational governance remains convergently stable"]

    if converged.get("governance_converged") and not recursion.get("stewardship_recursion_detected"):
        if finalization.get("governance_finalization_band") == "CONVERGED":
            return ["Governance convergence remains stable across stewardship layers"]

    return []
