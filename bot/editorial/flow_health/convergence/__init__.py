from __future__ import annotations

from typing import Any

from bot.editorial.flow_health.convergence.convergence import assess_governance_converged
from bot.editorial.flow_health.convergence.continuity import (
    is_convergence_day,
    touch_convergence_continuity,
)
from bot.editorial.flow_health.convergence.digest import build_convergence_digest_lines
from bot.editorial.flow_health.convergence.recursion import detect_stewardship_recursion
from bot.editorial.flow_health.convergence.saturation import compute_stewardship_novelty_decay
from bot.editorial.flow_health.convergence.stewardship import (
    compute_governance_finalization,
    evaluate_governance_finalization_candidate,
)


def convergence_snapshot(
    *,
    ctx: dict[str, Any] | None = None,
    governance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Stewardship convergence & governance finalization — advisory bundle."""
    gov = governance or (ctx or {}).get("flow_governance") or {}

    novelty = compute_stewardship_novelty_decay(governance=gov)
    recursion = detect_stewardship_recursion(governance=gov)
    converged = assess_governance_converged(governance=gov, novelty=novelty)
    convergence_today = is_convergence_day(
        converged=converged,
        recursion=recursion,
        novelty=novelty,
    )
    continuity = touch_convergence_continuity(converged_today=convergence_today)
    finalization = compute_governance_finalization(
        converged=converged,
        recursion=recursion,
        novelty=novelty,
        continuity=continuity,
        governance=gov,
    )
    candidate = evaluate_governance_finalization_candidate(
        converged=converged,
        recursion=recursion,
        novelty=novelty,
        continuity=continuity,
        finalization=finalization,
        governance=gov,
    )

    min_g = gov.get("minimalism") or {}
    obs = gov.get("observability") or {}
    clos = gov.get("closure") or {}
    finalization_quiet = bool(
        candidate.get("governance_finalization_candidate")
        and min_g.get("invisible_digest_mode")
        and obs.get("canonical_observability_quiet")
        and clos.get("operational_closure_candidate")
    )

    digest_lines = build_convergence_digest_lines(
        converged=converged,
        recursion=recursion,
        finalization=finalization,
        candidate=candidate,
        continuity=continuity,
        finalization_quiet=finalization_quiet,
    )

    return {
        "novelty": novelty,
        "stewardship_novelty_decay": novelty.get("stewardship_novelty_decay"),
        "recursion": recursion,
        "stewardship_recursion_detected": recursion.get("stewardship_recursion_detected"),
        "converged": converged,
        "governance_converged": converged.get("governance_converged"),
        "continuity": continuity,
        "governance_convergence_streak_days": continuity.get("governance_convergence_streak_days"),
        "governance_convergence_band": continuity.get("governance_convergence_band"),
        "finalization": finalization,
        "governance_finalization_index": finalization.get("governance_finalization_index"),
        "governance_finalization_band": finalization.get("governance_finalization_band"),
        "governance_finalization_candidate": candidate.get("governance_finalization_candidate"),
        "convergence_digest_lines": digest_lines,
        "finalization_digest_quiet": finalization_quiet,
    }


__all__ = ["convergence_snapshot"]
