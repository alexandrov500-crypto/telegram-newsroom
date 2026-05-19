from __future__ import annotations

import logging
from dataclasses import dataclass

from bot.epistemic.repository import EpistemicRepository
from bot.epistemic.schema import CONFIDENCE_DECAY_RATE

logger = logging.getLogger(__name__)

DEFAULT_TRUST = 0.5
TRUST_FLOOR = 0.1
TRUST_CEILING = 0.95


@dataclass(frozen=True)
class TrustEdge:
    from_node: str
    to_node: str
    trust_score: float
    reversible: bool
    reason: str


class TrustDecay:
    """Reversible trust decay — no permanent hidden penalties."""

    def __init__(self, repository: EpistemicRepository) -> None:
        self._repo = repository

    def apply_decay(self, from_node: str, to_node: str, *, reason: str) -> float:
        current = self._repo.get_trust(from_node, to_node)
        prior = float(current["trust_score"]) if current else DEFAULT_TRUST
        new_trust = max(TRUST_FLOOR, prior - CONFIDENCE_DECAY_RATE * 2)
        self._repo.upsert_trust(from_node, to_node, new_trust, reason=reason)
        return new_trust

    def restore(self, from_node: str, to_node: str, *, operator_id: str | None, reason: str) -> float:
        current = self._repo.get_trust(from_node, to_node)
        prior = float(current["trust_score"]) if current else DEFAULT_TRUST
        new_trust = min(TRUST_CEILING, prior + 0.1)
        self._repo.upsert_trust(
            from_node, to_node, new_trust, reason=reason, operator_id=operator_id,
        )
        return new_trust


class TrustGraph:
    """Trust-aware source and federation relationships."""

    def __init__(self, repository: EpistemicRepository) -> None:
        self._repo = repository
        self._decay = TrustDecay(repository)

    def update_from_contradiction(
        self,
        source: str,
        *,
        contradiction_count: int,
        correction_applied: bool = False,
    ) -> TrustEdge:
        node = f"source:{source}"
        mesh_node = "mesh:local"
        current = self._repo.get_trust(mesh_node, node)
        prior = float(current["trust_score"]) if current else DEFAULT_TRUST
        if correction_applied:
            new_trust = min(TRUST_CEILING, prior + 0.05)
            reason = "correction_applied"
        else:
            penalty = min(0.2, contradiction_count * 0.03)
            new_trust = max(TRUST_FLOOR, prior - penalty)
            reason = f"contradiction_frequency={contradiction_count}"
        self._repo.upsert_trust(mesh_node, node, new_trust, reason=reason, reversible=True)
        return TrustEdge(mesh_node, node, new_trust, True, reason)

    def weighted_consensus(
        self,
        votes: list[tuple[str, float, float]],
    ) -> tuple[float, str]:
        """Trust-weighted aggregation: (node, vote, trust)."""
        if not votes:
            return 0.5, "no votes"
        total = sum(v * t for _, v, t in votes)
        weight = sum(t for _, _, t in votes)
        score = total / weight if weight > 0 else 0.5
        return round(score, 4), f"trust-weighted from {len(votes)} nodes"

    def get_edge(self, from_node: str, to_node: str) -> TrustEdge | None:
        row = self._repo.get_trust(from_node, to_node)
        if not row:
            return None
        return TrustEdge(
            from_node,
            to_node,
            float(row["trust_score"]),
            bool(row["reversible"]),
            str(row["reason"]),
        )

    def operator_override(
        self,
        from_node: str,
        to_node: str,
        trust: float,
        *,
        operator_id: str | None,
        reason: str,
    ) -> TrustEdge:
        trust = max(TRUST_FLOOR, min(TRUST_CEILING, trust))
        self._repo.upsert_trust(
            from_node, to_node, trust, reason=reason, operator_id=operator_id,
        )
        return TrustEdge(from_node, to_node, trust, True, f"operator_override: {reason}")
