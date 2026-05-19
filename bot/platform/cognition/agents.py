from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentVote:
    agent_id: str
    role: str
    score: float
    reason: str


@dataclass
class EditorialDebate:
    story_id: int
    votes: list[AgentVote] = field(default_factory=list)
    consensus: float = 0.0
    summary: str = ""

    def add_vote(self, vote: AgentVote) -> None:
        self.votes.append(vote)

    def finalize(self) -> None:
        if not self.votes:
            return
        self.consensus = sum(v.score for v in self.votes) / len(self.votes)
        self.summary = "; ".join(f"{v.agent_id}={v.score:.2f}" for v in self.votes)


@dataclass
class MultiAgentCognitionOrchestrator:
    """Specialized agents with debate summaries — explainable, bounded."""

    _debates: dict[int, EditorialDebate] = field(default_factory=dict)
    _agent_metrics: dict[str, list[float]] = field(default_factory=dict)

    def run_debate(
        self,
        story_id: int,
        *,
        source_trust: float = 0.8,
        contradiction: float = 0.1,
        confidence: float = 0.85,
    ) -> EditorialDebate:
        debate = EditorialDebate(story_id=story_id)
        agents = (
            ("trust_agent", "trust", source_trust, "source reputation"),
            ("epistemic_agent", "epistemic", 1.0 - contradiction, "contradiction check"),
            ("confidence_agent", "model", confidence, "model confidence"),
            ("style_agent", "style", 0.75, "editorial style fit"),
        )
        for aid, role, score, reason in agents:
            debate.add_vote(AgentVote(aid, role, score, reason))
            self._agent_metrics.setdefault(aid, []).append(score)
        debate.finalize()
        self._debates[story_id] = debate
        return debate

    def mesh_text(self) -> str:
        lines = ["<b>Agent mesh</b>"]
        for aid, scores in list(self._agent_metrics.items())[:6]:
            avg = sum(scores) / len(scores) if scores else 0
            lines.append(f"• {aid}: avg {avg:.2f} (n={len(scores)})")
        if not self._agent_metrics:
            lines.append("No debates yet — triggered on cognition paths.")
        return "\n".join(lines)

    def debate_trace_text(self, story_id: int) -> str:
        d = self._debates.get(story_id)
        if d is None:
            d = self.run_debate(story_id)
        lines = [
            f"<b>Debate trace</b> #{story_id}",
            f"Consensus {d.consensus:.2f}",
            d.summary,
        ]
        for v in d.votes:
            lines.append(f"• {v.agent_id} ({v.role}): {v.reason}")
        return "\n".join(lines)
