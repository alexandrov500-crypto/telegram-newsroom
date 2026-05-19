from __future__ import annotations

import logging
from dataclasses import dataclass, field

from bot.cognitive.repository import CognitiveRepository
from bot.cognitive.types import AgentSpec

logger = logging.getLogger(__name__)

DEFAULT_AGENTS: tuple[AgentSpec, ...] = (
    AgentSpec("breaking_news", "Breaking News Agent", ("detect", "prioritize", "publish_hint")),
    AgentSpec("fact_check", "Fact-Checking Agent", ("verify", "flag_inconsistency")),
    AgentSpec("geopolitical", "Geopolitical Analysis Agent", ("analyze_region", "entity_link")),
    AgentSpec("trend", "Trend Detection Agent", ("detect_trend", "velocity")),
    AgentSpec("quality_review", "Quality Review Agent", ("evaluate", "block_low_quality")),
    AgentSpec("digest_curation", "Digest Curation Agent", ("rank", "assemble_digest")),
    AgentSpec("anomaly", "Anomaly Detection Agent", ("detect_anomaly", "alert")),
)


@dataclass
class AgentProposal:
    agent_id: str
    action: str
    confidence: float
    reason: str
    bounded: bool = True


class AgentRegistry:
    """Registry of specialized editorial agents with capability negotiation."""

    def __init__(self, repository: CognitiveRepository) -> None:
        self._repo = repository
        self._ensure_defaults()

    def _ensure_defaults(self) -> None:
        existing = {a["agent_id"] for a in self._repo.list_agents()}
        for spec in DEFAULT_AGENTS:
            if spec.agent_id not in existing:
                self._repo.register_agent(
                    spec.agent_id,
                    spec.name,
                    list(spec.capabilities),
                    spec.autonomy_bound,
                )

    def list_specs(self) -> list[AgentSpec]:
        return [
            AgentSpec(
                r["agent_id"],
                r["name"],
                tuple(r.get("capabilities") or []),
                int(r.get("autonomy_bound") or 1),
            )
            for r in self._repo.list_agents()
        ]

    def negotiate(self, required_capabilities: list[str]) -> list[AgentSpec]:
        req = set(required_capabilities)
        return [s for s in self.list_specs() if req <= set(s.capabilities)]

    def can_execute(self, agent_id: str, action: str) -> bool:
        for spec in self.list_specs():
            if spec.agent_id == agent_id:
                return action in spec.capabilities or action == "evaluate"
        return False


@dataclass
class AgentCoordinationSession:
    session_id: str
    proposals: list[AgentProposal] = field(default_factory=list)


class MultiAgentCoordinator:
    """Event-driven multi-agent coordination with bounded autonomy."""

    def __init__(self, registry: AgentRegistry) -> None:
        self._registry = registry
        self._max_proposals_per_cycle = 5

    async def coordinate(
        self,
        *,
        context: dict,
        required_capabilities: list[str] | None = None,
    ) -> AgentCoordinationSession:
        import uuid

        session = AgentCoordinationSession(session_id=str(uuid.uuid4())[:12])
        caps = required_capabilities or ["evaluate"]
        agents = self._registry.negotiate(caps)[: self._max_proposals_per_cycle]
        importance = float(context.get("importance_score") or 0.5)
        for spec in agents:
            proposal = self._propose(spec, context, importance)
            if proposal:
                session.proposals.append(proposal)
        return session

    def _propose(self, spec: AgentSpec, context: dict, importance: float) -> AgentProposal | None:
        if spec.agent_id == "breaking_news" and importance > 0.8:
            return AgentProposal(
                spec.agent_id,
                "prioritize",
                confidence=0.85,
                reason="high importance breaking pattern",
            )
        if spec.agent_id == "quality_review":
            score = float(context.get("evaluation_score") or 0.6)
            if score < 0.5:
                return AgentProposal(
                    spec.agent_id,
                    "block_low_quality",
                    confidence=0.7,
                    reason=f"evaluation_score={score:.2f}",
                )
        if spec.agent_id == "anomaly" and context.get("anomaly_flag"):
            return AgentProposal(
                spec.agent_id,
                "alert",
                confidence=0.9,
                reason="anomaly detected in signals",
            )
        if spec.agent_id == "digest_curation" and context.get("digest_candidate"):
            return AgentProposal(
                spec.agent_id,
                "rank",
                confidence=0.75,
                reason="digest scheduling window",
            )
        return None
