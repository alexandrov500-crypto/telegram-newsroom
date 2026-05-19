from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AgentVote:
    agent_id: str
    score: float
    reason: str


@dataclass
class EditorialVoteResult:
    consensus_score: float
    votes: tuple[AgentVote, ...]
    decision: str
    explain: str


@dataclass
class StoryTimeline:
    story_id: int
    events: list[dict[str, Any]] = field(default_factory=list)
    freshness_score: float = 1.0
    confidence_decay: float = 0.0
    narrative_drift: float = 0.0

    def append(self, kind: str, detail: str, *, ref: str | None = None) -> None:
        self.events.append(
            {
                "at": time.time(),
                "kind": kind,
                "detail": detail[:300],
                "ref": ref,
            },
        )
        self._recompute()

    def _recompute(self) -> None:
        if not self.events:
            return
        age_hours = (time.time() - self.events[0]["at"]) / 3600.0
        self.freshness_score = max(0.1, 1.0 - age_hours / 72.0)
        self.confidence_decay = min(1.0, age_hours / 48.0)
        kinds = [e["kind"] for e in self.events[-5:]]
        self.narrative_drift = 0.3 if len(set(kinds)) >= 4 else 0.0


class CognitionEvolutionOrchestrator:
    """Multi-agent voting, timelines, contradiction hints — explainable, replay-safe."""

    def __init__(self) -> None:
        self._timelines: dict[int, StoryTimeline] = {}

    def vote_editorial(
        self,
        *,
        story_id: int,
        source_trust: float,
        contradiction_score: float,
        confidence: float,
    ) -> EditorialVoteResult:
        votes = (
            AgentVote("trust", source_trust, "source reputation"),
            AgentVote("epistemic", 1.0 - contradiction_score, "contradiction check"),
            AgentVote("confidence", confidence, "model confidence"),
        )
        consensus = sum(v.score for v in votes) / len(votes)
        if consensus >= 0.75:
            decision = "approve_candidate"
        elif consensus >= 0.5:
            decision = "review"
        else:
            decision = "block"
        explain = "; ".join(f"{v.agent_id}={v.score:.2f}" for v in votes)
        tl = self._timelines.setdefault(story_id, StoryTimeline(story_id=story_id))
        tl.append("vote", decision, ref=explain)
        return EditorialVoteResult(
            consensus_score=consensus,
            votes=votes,
            decision=decision,
            explain=explain,
        )

    def detect_source_contradiction(
        self,
        *,
        story_id: int,
        claims: list[str],
    ) -> float:
        if len(claims) < 2:
            return 0.0
        tokens_a = set(claims[0].lower().split())
        tokens_b = set(claims[1].lower().split())
        overlap = len(tokens_a & tokens_b) / max(len(tokens_a | tokens_b), 1)
        contradiction = 1.0 - overlap if len(claims) >= 2 else 0.0
        if contradiction > 0.6:
            self._timelines.setdefault(story_id, StoryTimeline(story_id=story_id)).append(
                "contradiction",
                f"claims diverge score={contradiction:.2f}",
            )
        return contradiction

    def timeline(self, story_id: int) -> StoryTimeline:
        return self._timelines.setdefault(story_id, StoryTimeline(story_id=story_id))

    def summary_text(self, story_id: int) -> str:
        tl = self.timeline(story_id)
        lines = [
            f"<b>Story evolution</b> #{story_id}",
            f"Freshness {tl.freshness_score:.2f} · drift {tl.narrative_drift:.2f}",
        ]
        for ev in tl.events[-6:]:
            lines.append(f"• {ev['kind']}: {ev['detail'][:80]}")
        return "\n".join(lines)
