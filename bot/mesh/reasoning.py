from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field

from bot.mesh.repository import MeshRepository
from bot.mesh.types import ConsensusVote, ReasoningSessionResult

logger = logging.getLogger(__name__)


@dataclass
class CollaborativeReasoningSession:
    session_id: str
    topic: str
    region: str
    votes: list[ConsensusVote] = field(default_factory=list)


class CollectiveReasoningEngine:
    """Auditable collaborative reasoning with consensus and minority preservation."""

    def __init__(self, repository: MeshRepository, *, node_id: str, region: str) -> None:
        self._repo = repository
        self._node_id = node_id
        self._region = region

    def open_session(self, topic: str, *, context: dict | None = None) -> CollaborativeReasoningSession:
        session_id = str(uuid.uuid4())[:12]
        audit = {"opened_by": self._node_id, "context": context or {}}
        self._repo.create_reasoning_session(session_id, topic, self._region, audit)
        return CollaborativeReasoningSession(session_id=session_id, topic=topic, region=self._region)

    def submit_vote(
        self,
        session: CollaborativeReasoningSession,
        vote: ConsensusVote,
    ) -> None:
        session.votes.append(vote)
        self._repo.add_consensus_vote(
            session.session_id,
            node_id=vote.node_id,
            vote=vote.vote,
            confidence=vote.confidence,
            reason=vote.reason,
            agent_id=vote.agent_id,
        )

    def finalize(self, session: CollaborativeReasoningSession) -> ReasoningSessionResult:
        votes = self._repo.get_session_votes(session.session_id)
        if not votes:
            return ReasoningSessionResult(
                session_id=session.session_id,
                consensus_score=0.0,
                confidence=0.0,
                disagreement=[],
                minority_opinions=[],
                explanation="no votes recorded",
            )

        weighted_sum = 0.0
        weight_total = 0.0
        for v in votes:
            w = float(v["confidence"])
            weighted_sum += float(v["vote"]) * w
            weight_total += w
        consensus = weighted_sum / weight_total if weight_total > 0 else 0.0

        mean_vote = sum(float(v["vote"]) for v in votes) / len(votes)
        disagreement = [
            {
                "node_id": v["node_id"],
                "vote": v["vote"],
                "delta_from_consensus": round(float(v["vote"]) - consensus, 4),
                "reason": v["reason"],
            }
            for v in votes
            if abs(float(v["vote"]) - consensus) > 0.15
        ]
        minority = [
            {"node_id": v["node_id"], "vote": v["vote"], "reason": v["reason"]}
            for v in votes
            if abs(float(v["vote"]) - mean_vote) > 0.25
        ]

        confidence = min(1.0, weight_total / len(votes))
        explanation = (
            f"weighted consensus {consensus:.3f} from {len(votes)} votes; "
            f"{len(disagreement)} disagreements; {len(minority)} minority preserved"
        )

        self._repo.complete_reasoning_session(
            session.session_id,
            consensus_score=consensus,
            disagreement=disagreement,
            minority=minority,
        )
        return ReasoningSessionResult(
            session_id=session.session_id,
            consensus_score=round(consensus, 4),
            confidence=round(confidence, 4),
            disagreement=disagreement,
            minority_opinions=minority,
            explanation=explanation,
        )

    async def co_evaluate_story(
        self,
        *,
        story_id: int,
        title: str,
        regional_votes: list[tuple[str, float, str]],
    ) -> ReasoningSessionResult:
        session = self.open_session(f"story:{story_id}", context={"title": title[:120]})
        for node_id, score, reason in regional_votes:
            self.submit_vote(
                session,
                ConsensusVote(node_id=node_id, vote=score, confidence=0.8, reason=reason),
            )
        return self.finalize(session)
