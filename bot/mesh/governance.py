from __future__ import annotations

import logging
from dataclasses import dataclass

from bot.mesh.repository import MeshRepository
from bot.mesh.types import ConstitutionalPolicyDocument

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GovernanceDecision:
    allowed: bool
    reason: str
    invariant: str | None = None


class ConstitutionalGovernance:
    """First-class governance constraints for autonomous cognition."""

    def __init__(self, repository: MeshRepository) -> None:
        self._repo = repository

    @property
    def constitution(self) -> ConstitutionalPolicyDocument | None:
        return self._repo.get_active_constitution()

    def check_action(self, action: str, *, context: dict | None = None) -> GovernanceDecision:
        doc = self.constitution
        if doc is None:
            return GovernanceDecision(True, "no constitution loaded")

        if action in doc.protected_actions:
            if doc.require_operator_for_policy_change:
                operator = (context or {}).get("operator_approved", False)
                if not operator:
                    return GovernanceDecision(
                        False,
                        f"protected action '{action}' requires operator",
                        invariant="operator_supremacy",
                    )

        if action == "production_cognition_mutate" and doc.require_simulation_before_promotion:
            simulated = (context or {}).get("simulation_passed", False)
            if not simulated:
                return GovernanceDecision(
                    False,
                    "promotion requires simulation gate",
                    invariant="simulation_before_promotion",
                )

        autonomy = int((context or {}).get("autonomy_level", 0))
        if autonomy > doc.max_autonomy_level:
            return GovernanceDecision(
                False,
                f"autonomy {autonomy} exceeds max {doc.max_autonomy_level}",
                invariant="bounded_autonomy",
            )

        explainable_actions = {
            "production_cognition_mutate",
            "constitutional_amend",
            "mesh_consensus_publish",
        }
        if (
            action in explainable_actions
            and doc.explainability_required
            and not (context or {}).get("explanation")
        ):
            return GovernanceDecision(
                False,
                "explainability required",
                invariant="explainability",
            )

        return GovernanceDecision(True, "allowed")

    def allow_simulation(self, lane: str) -> bool:
        return lane in ("shadow", "offline", "tournament", "mesh_shadow")

    def allow_learning_apply(self, *, operator_approved: bool = False) -> GovernanceDecision:
        return self.check_action(
            "policy_change",
            context={"operator_approved": operator_approved},
        )

    def allow_mesh_publish(self, event_type: str) -> GovernanceDecision:
        if event_type.startswith("policy."):
            return self.check_action("policy_change")
        return GovernanceDecision(True, "cognitive event allowed")
