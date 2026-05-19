from __future__ import annotations

from dataclasses import dataclass

from bot.epistemic.repository import EpistemicRepository
from bot.epistemic.types import EpistemicGovernanceDocument, EpistemicScore


@dataclass(frozen=True)
class EpistemicGovernanceDecision:
    allowed: bool
    reason: str
    invariant: str | None = None
    requires_disclosure: bool = False


class EpistemicGovernance:
    """Constitutional extensions for truth integrity and uncertainty disclosure."""

    def __init__(self, repository: EpistemicRepository) -> None:
        self._repo = repository

    @property
    def policy(self) -> EpistemicGovernanceDocument | None:
        return self._repo.get_active_governance()

    def validate_score(self, score: EpistemicScore) -> EpistemicGovernanceDecision:
        doc = self.policy
        if doc is None:
            return EpistemicGovernanceDecision(True, "no policy")

        if score.confidence > doc.anti_overconfidence_cap:
            return EpistemicGovernanceDecision(
                False,
                f"confidence {score.confidence:.2f} exceeds cap {doc.anti_overconfidence_cap}",
                invariant="anti_overconfidence",
            )

        if score.evidence_depth < 0.3 and score.confidence > doc.max_confidence_without_evidence:
            return EpistemicGovernanceDecision(
                False,
                "insufficient evidence for confidence level",
                invariant="truth_integrity",
            )

        disclosure = doc.require_uncertainty_disclosure and score.uncertainty < 0.1
        return EpistemicGovernanceDecision(
            True,
            "score valid",
            requires_disclosure=disclosure,
        )

    def allow_consensus_resolution(self, *, has_open_contradictions: bool) -> EpistemicGovernanceDecision:
        doc = self.policy
        if doc and doc.preserve_contradictions and has_open_contradictions:
            return EpistemicGovernanceDecision(
                False,
                "open contradictions must be preserved — no forced consensus",
                invariant="minority_preservation",
            )
        return EpistemicGovernanceDecision(True, "consensus allowed")

    def allow_trust_update(self, *, operator_approved: bool = False) -> EpistemicGovernanceDecision:
        return EpistemicGovernanceDecision(
            True,
            "trust update allowed (reversible)",
        )

    def require_operator_for_alert_escalation(self, severity: float) -> bool:
        return severity > 0.75
