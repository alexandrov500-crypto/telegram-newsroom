from __future__ import annotations

from typing import Any

from bot.editorial.flow_health.legacy.continuity import touch_legacy_memory
from bot.editorial.flow_health.legacy.dependency import assess_stewardship_dependency_risk
from bot.editorial.flow_health.legacy.digest import build_legacy_digest_lines
from bot.editorial.flow_health.legacy.legibility import compute_operational_legibility
from bot.editorial.flow_health.legacy.stewardship import assess_institutional_transferability
from bot.editorial.flow_health.legacy.succession import evaluate_succession_readiness


def legacy_snapshot(
    *,
    ctx: dict[str, Any] | None = None,
    governance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Operational legacy & stewardship succession — advisory bundle."""
    gov = governance or (ctx or {}).get("flow_governance") or {}

    dependency = assess_stewardship_dependency_risk(governance=gov)
    legibility = compute_operational_legibility(governance=gov, dependency=dependency)
    succession = evaluate_succession_readiness(
        governance=gov,
        dependency=dependency,
        legibility=legibility,
    )
    transferability = assess_institutional_transferability(
        dependency=dependency,
        legibility=legibility,
        succession=succession,
        governance=gov,
    )
    clos = gov.get("closure") or {}
    explain_gap = legibility.get("operational_legibility_band") == "OPAQUE"
    memory = touch_legacy_memory(
        dependency_risk=str(dependency.get("stewardship_dependency_risk", "LOW")),
        succession_safe=bool(succession.get("succession_readiness")),
        explainability_gap=explain_gap,
    )
    digest_lines = build_legacy_digest_lines(
        succession=succession,
        legibility=legibility,
        dependency=dependency,
        transferability=transferability,
        closure_ready=bool(clos.get("operational_closure_candidate") or clos.get("architectural_sufficiency")),
    )

    return {
        "stewardship_dependency": dependency,
        "stewardship_dependency_risk": dependency.get("stewardship_dependency_risk"),
        "operational_legibility": legibility,
        "operational_legibility_index": legibility.get("operational_legibility_index"),
        "operational_legibility_band": legibility.get("operational_legibility_band"),
        "succession": succession,
        "succession_readiness": succession.get("succession_readiness"),
        "institutional_transferability": transferability,
        "institutional_transferability_band": transferability.get("institutional_transferability_band"),
        "legacy_memory": memory,
        "legacy_digest_lines": digest_lines,
    }


__all__ = ["legacy_snapshot"]
