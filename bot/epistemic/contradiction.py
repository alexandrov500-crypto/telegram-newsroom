from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field

from bot.epistemic.repository import EpistemicRepository
from bot.epistemic.types import ContradictionRecord

logger = logging.getLogger(__name__)


@dataclass
class ContradictionCluster:
    cluster_id: str
    claims: list[dict] = field(default_factory=list)
    regions: set[str] = field(default_factory=set)


class ContradictionGraph:
    """Distributed contradiction analysis with lineage and minority preservation."""

    def __init__(self, repository: EpistemicRepository) -> None:
        self._repo = repository

    @staticmethod
    def cluster_key(subject_type: str, subject_id: str) -> str:
        return hashlib.sha256(f"{subject_type}:{subject_id}".encode()).hexdigest()[:16]

    def detect_pair(
        self,
        *,
        subject_type: str,
        subject_id: str,
        claim_a: str,
        claim_b: str,
        region_a: str | None = None,
        region_b: str | None = None,
        score_a: float = 0.5,
        score_b: float = 0.5,
    ) -> ContradictionRecord | None:
        delta = abs(score_a - score_b)
        if delta < 0.2 and claim_a[:50].lower() == claim_b[:50].lower():
            return None

        severity = min(1.0, delta + (0.1 if region_a != region_b else 0))
        cluster_id = self.cluster_key(subject_type, subject_id)
        minority = [
            {"claim": claim_b, "region": region_b, "score": score_b},
        ] if score_a >= score_b else [
            {"claim": claim_a, "region": region_a, "score": score_a},
        ]
        explanation = (
            f"Conflicting claims on {subject_type}:{subject_id} "
            f"(delta={delta:.2f}, regional={'yes' if region_a != region_b else 'no'})"
        )
        cid = self._repo.create_contradiction(
            cluster_id=cluster_id,
            subject_type=subject_type,
            severity=severity,
            explanation=explanation,
            minority_views=minority,
        )
        self._repo.add_contradiction_edge(cid, claim_a[:200], claim_b[:200], "conflicts", region=region_a)
        if region_b:
            self._repo.add_contradiction_edge(cid, claim_b[:200], claim_a[:200], "conflicts", region=region_b)
        return ContradictionRecord(
            contradiction_id=cid,
            cluster_id=cluster_id,
            subject_type=subject_type,
            severity=severity,
            explanation=explanation,
            minority_views=tuple(minority),
        )

    def detect_memory_divergence(
        self,
        memory_id: str,
        shards: list[dict],
    ) -> ContradictionRecord | None:
        if len(shards) < 2:
            return None
        payloads = [s.get("payload", {}) for s in shards]
        titles = [p.get("title", "") for p in payloads]
        if len(set(titles)) <= 1:
            return None
        return self.detect_pair(
            subject_type="memory",
            subject_id=memory_id,
            claim_a=titles[0],
            claim_b=titles[1],
            region_a=shards[0].get("region"),
            region_b=shards[1].get("region") if len(shards) > 1 else None,
        )

    def detect_consensus_disagreement(
        self,
        session_id: str,
        votes: list[dict],
        *,
        escalation_threshold: float = 0.25,
    ) -> ContradictionRecord | None:
        if len(votes) < 2:
            return None
        values = [float(v["vote"]) for v in votes]
        spread = max(values) - min(values)
        if spread < escalation_threshold:
            return None
        minority = [
            {"node_id": v["node_id"], "vote": v["vote"], "reason": v["reason"]}
            for v in votes
            if float(v["vote"]) < sum(values) / len(values) - 0.1
        ]
        cluster_id = self.cluster_key("consensus", session_id)
        explanation = f"Consensus disagreement spread={spread:.2f} across {len(votes)} votes"
        cid = self._repo.create_contradiction(
            cluster_id=cluster_id,
            subject_type="consensus",
            severity=min(1.0, spread),
            explanation=explanation,
            minority_views=minority,
        )
        return ContradictionRecord(
            contradiction_id=cid,
            cluster_id=cluster_id,
            subject_type="consensus",
            severity=spread,
            explanation=explanation,
            minority_views=tuple(minority),
        )

    def open_contradictions(self, limit: int = 15) -> list[dict]:
        return self._repo.open_contradictions(limit=limit)

    def lineage(self, contradiction_id: str) -> list[dict]:
        with self._repo._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM epistemic_contradiction_edges
                WHERE contradiction_id = ? ORDER BY created_at
                """,
                (contradiction_id,),
            ).fetchall()
        return [dict(r) for r in rows]
