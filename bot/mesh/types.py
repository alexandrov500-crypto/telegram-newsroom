from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


COGNITIVE_LANES = frozenset({"gossip", "quorum", "regional", "evaluation", "memory", "learning"})


@dataclass(frozen=True)
class MeshAgentLease:
    lease_id: str
    agent_id: str
    holder_node: str
    region: str
    capabilities: tuple[str, ...]
    expires_at: str


@dataclass
class ConsensusVote:
    node_id: str
    vote: float
    confidence: float
    reason: str
    agent_id: str | None = None


@dataclass
class ReasoningSessionResult:
    session_id: str
    consensus_score: float
    confidence: float
    disagreement: list[dict[str, Any]]
    minority_opinions: list[dict[str, Any]]
    explanation: str


@dataclass
class MemoryShardRecord:
    shard_id: str
    region: str
    memory_id: str
    payload: dict[str, Any]
    vector_clock: dict[str, int]


@dataclass
class ConstitutionalPolicyDocument:
    policy_id: str
    version: int
    invariants: list[str] = field(default_factory=list)
    max_autonomy_level: int = 2
    require_operator_for_policy_change: bool = True
    require_simulation_before_promotion: bool = True
    explainability_required: bool = True
    protected_actions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "version": self.version,
            "invariants": self.invariants,
            "max_autonomy_level": self.max_autonomy_level,
            "require_operator_for_policy_change": self.require_operator_for_policy_change,
            "require_simulation_before_promotion": self.require_simulation_before_promotion,
            "explainability_required": self.explainability_required,
            "protected_actions": self.protected_actions,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ConstitutionalPolicyDocument:
        return cls(
            policy_id=str(data.get("policy_id", "mesh_constitution")),
            version=int(data.get("version", 1)),
            invariants=list(data.get("invariants") or []),
            max_autonomy_level=int(data.get("max_autonomy_level", 2)),
            require_operator_for_policy_change=bool(
                data.get("require_operator_for_policy_change", True)
            ),
            require_simulation_before_promotion=bool(
                data.get("require_simulation_before_promotion", True)
            ),
            explainability_required=bool(data.get("explainability_required", True)),
            protected_actions=list(data.get("protected_actions") or []),
        )
