from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from bot.cognitive.agents import AgentRegistry
from bot.mesh.envelope import CognitiveEventEnvelope
from bot.mesh.repository import MeshRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentMarketOffer:
    agent_id: str
    node_id: str
    region: str
    capabilities: tuple[str, ...]
    load_score: float


class AgentMeshRegistry:
    """Distributed agent fabric with leases and capability marketplace."""

    def __init__(
        self,
        mesh_repo: MeshRepository,
        local_registry: AgentRegistry,
        *,
        node_id: str,
        region: str,
    ) -> None:
        self._mesh = mesh_repo
        self._local = local_registry
        self._node_id = node_id
        self._region = region

    def advertise_capabilities(self) -> list[AgentMarketOffer]:
        offers: list[AgentMarketOffer] = []
        for spec in self._local.list_specs():
            lease_id = f"{self._node_id}:{spec.agent_id}"
            acquired = self._mesh.acquire_agent_lease(
                lease_id=lease_id,
                agent_id=spec.agent_id,
                holder_node=self._node_id,
                region=self._region,
                capabilities=list(spec.capabilities),
            )
            if acquired:
                offers.append(
                    AgentMarketOffer(
                        agent_id=spec.agent_id,
                        node_id=self._node_id,
                        region=self._region,
                        capabilities=spec.capabilities,
                        load_score=0.3,
                    )
                )
        return offers

    def marketplace(self, *, required: list[str] | None = None) -> list[AgentMarketOffer]:
        leases = self._mesh.list_agent_leases()
        offers: list[AgentMarketOffer] = []
        for lease in leases:
            caps = tuple(lease.get("capabilities") or [])
            if required and not set(required) <= set(caps):
                continue
            offers.append(
                AgentMarketOffer(
                    agent_id=lease["agent_id"],
                    node_id=lease["holder_node"],
                    region=lease["region"],
                    capabilities=caps,
                    load_score=0.5,
                )
            )
        return sorted(offers, key=lambda o: o.load_score)

    def allocate_task(
        self,
        *,
        required_capabilities: list[str],
        prefer_region: str | None = None,
    ) -> AgentMarketOffer | None:
        offers = self.marketplace(required=required_capabilities)
        if prefer_region:
            regional = [o for o in offers if o.region == prefer_region]
            if regional:
                offers = regional
        return offers[0] if offers else None

    def migrate_agent(self, agent_id: str, *, target_region: str) -> bool:
        lease_id = f"{self._node_id}:{agent_id}:migrate"
        spec = next((s for s in self._local.list_specs() if s.agent_id == agent_id), None)
        if spec is None:
            return False
        return self._mesh.acquire_agent_lease(
            lease_id=lease_id,
            agent_id=agent_id,
            holder_node=self._node_id,
            region=target_region,
            capabilities=list(spec.capabilities),
        )

    async def share_evaluation(
        self,
        bus: object,
        *,
        evaluation_id: str,
        score: float,
        target_id: str,
    ) -> None:
        if not hasattr(bus, "publish"):
            return
        env = CognitiveEventEnvelope(
            event_type="agent.evaluation_shared",
            payload={
                "evaluation_id": evaluation_id,
                "score": score,
                "target_id": target_id,
                "agent_node": self._node_id,
            },
            lane="evaluation",
            node_id=self._node_id,
            region=self._region,
        )
        await bus.publish(env)

    def trace_lineage(self, agent_id: str) -> list[dict]:
        return [
            {
                "agent_id": l["agent_id"],
                "holder": l["holder_node"],
                "region": l["region"],
                "expires": l["expires_at"],
            }
            for l in self._mesh.list_agent_leases()
            if l["agent_id"] == agent_id
        ]
