from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EpistemicScore:
    """Explainable confidence primitive attached to cognitive artifacts."""

    score_id: str
    subject_type: str
    subject_id: str
    confidence: float
    uncertainty: float
    evidence_depth: float
    contradiction_exposure: float
    source_diversity: float
    replay_stability: float
    explanation: str
    replay_key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "score_id": self.score_id,
            "subject_type": self.subject_type,
            "subject_id": self.subject_id,
            "confidence": self.confidence,
            "uncertainty": self.uncertainty,
            "evidence_depth": self.evidence_depth,
            "contradiction_exposure": self.contradiction_exposure,
            "source_diversity": self.source_diversity,
            "replay_stability": self.replay_stability,
            "explanation": self.explanation,
            "replay_key": self.replay_key,
        }


@dataclass(frozen=True)
class ContradictionRecord:
    contradiction_id: str
    cluster_id: str
    subject_type: str
    severity: float
    explanation: str
    minority_views: tuple[dict[str, Any], ...] = ()


@dataclass(frozen=True)
class MisinformationAlert:
    alert_id: str
    alert_type: str
    severity: float
    subject_id: str
    explanation: str
    requires_review: bool = True


@dataclass
class EpistemicGovernanceDocument:
    policy_id: str
    version: int
    invariants: list[str] = field(default_factory=list)
    max_confidence_without_evidence: float = 0.75
    require_uncertainty_disclosure: bool = True
    preserve_contradictions: bool = True
    anti_overconfidence_cap: float = 0.95
    anti_manipulation_rules: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "version": self.version,
            "invariants": self.invariants,
            "max_confidence_without_evidence": self.max_confidence_without_evidence,
            "require_uncertainty_disclosure": self.require_uncertainty_disclosure,
            "preserve_contradictions": self.preserve_contradictions,
            "anti_overconfidence_cap": self.anti_overconfidence_cap,
            "anti_manipulation_rules": self.anti_manipulation_rules,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EpistemicGovernanceDocument:
        return cls(
            policy_id=str(data.get("policy_id", "epistemic_default")),
            version=int(data.get("version", 1)),
            invariants=list(data.get("invariants") or []),
            max_confidence_without_evidence=float(
                data.get("max_confidence_without_evidence", 0.75)
            ),
            require_uncertainty_disclosure=bool(
                data.get("require_uncertainty_disclosure", True)
            ),
            preserve_contradictions=bool(data.get("preserve_contradictions", True)),
            anti_overconfidence_cap=float(data.get("anti_overconfidence_cap", 0.95)),
            anti_manipulation_rules=list(data.get("anti_manipulation_rules") or []),
        )
