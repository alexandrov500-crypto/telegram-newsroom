from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bot.cognitive.runtime import CognitiveEditorialRuntime
from bot.mesh.agents import AgentMeshRegistry
from bot.mesh.bus import FederatedCognitiveBus
from bot.mesh.economics import IntelligenceEconomics
from bot.mesh.governance import ConstitutionalGovernance
from bot.mesh.learning import FederatedLearningMesh
from bot.mesh.memory import FederatedCognitiveMemory
from bot.mesh.observability import MeshObservability
from bot.mesh.reasoning import CollectiveReasoningEngine
from bot.mesh.repository import MeshRepository
from bot.mesh.resilience import CognitiveResilienceService
from bot.mesh.simulation import FederatedSimulationArena

logger = logging.getLogger(__name__)


@dataclass
class FederatedCognitiveMesh:
    """Distributed collaborative intelligence mesh facade."""

    repository: MeshRepository
    bus: FederatedCognitiveBus
    agents: AgentMeshRegistry
    memory: FederatedCognitiveMemory
    reasoning: CollectiveReasoningEngine
    learning: FederatedLearningMesh
    resilience: CognitiveResilienceService
    simulation: FederatedSimulationArena
    economics: IntelligenceEconomics
    governance: ConstitutionalGovernance
    observability: MeshObservability
    cognitive: CognitiveEditorialRuntime
    node_id: str
    region: str

    async def tick(
        self,
        *,
        is_leader: bool = False,
        mesh_pressure: float = 0.0,
        regional_pressures: dict[str, float] | None = None,
        stale_evaluations: int = 0,
        apply_gossip: bool = True,
    ) -> dict[str, Any]:
        self.bus.reset_tick_budget()

        health = self.resilience.assess(stale_eval_count=stale_evaluations)
        econ = self.economics.decide(mesh_pressure=mesh_pressure, importance=0.5)
        offers = self.agents.advertise_capabilities() if econ.allow else []

        propagated = 0
        if apply_gossip and is_leader:
            recent = self.repository.recent_events(region=self.region, limit=10)
            from bot.mesh.envelope import CognitiveEventEnvelope

            envelopes = []
            for row in recent:
                if row["origin_node"] == self.node_id:
                    continue
                try:
                    import json

                    payload = json.loads(row["payload_json"])
                    envelopes.append(
                        CognitiveEventEnvelope(
                            event_id=row["event_id"],
                            event_type=row["event_type"],
                            payload=payload,
                            lane=row["lane"],
                            node_id=row["origin_node"],
                            region=row["region"],
                            sequence_num=int(row["sequence_num"]),
                            ttl_hops=2,
                        )
                    )
                except (json.JSONDecodeError, KeyError):
                    continue
            propagated = await self.bus.propagate_gossip(envelopes)

        if self.federated_sync_available():
            pending = self.learning.aggregate_pending()
            if pending.get("aggregated", 0) > 0 and is_leader:
                self.learning.sync_to_cluster("aggregated", pending)

        snap = self.observability.build_snapshot(
            node_id=self.node_id,
            region=self.region,
            regional_pressures=regional_pressures,
        )
        balance = self.economics.balance_pressure(regional_pressures or {})

        report: dict[str, Any] = {
            "mesh_health": health.mesh_health,
            "agent_offers": len(offers),
            "gossip_propagated": propagated,
            "economics": econ.reason,
            "recommendations": list(health.recommendations),
            "pressure_balance": balance,
            "events_recent": snap.propagation_graph.get("recent_events", 0),
        }
        self.repository.save_observability_snapshot(
            "mesh_tick",
            {"node_id": self.node_id, "report": report},
        )
        return report

    def federated_sync_available(self) -> bool:
        return getattr(self.learning, "_federated", None) is not None

    async def publish_cognitive(
        self,
        event_type: str,
        payload: dict,
        *,
        lane: str = "gossip",
    ) -> bool:
        from bot.mesh.envelope import CognitiveEventEnvelope

        decision = self.governance.allow_mesh_publish(event_type)
        if not decision.allowed:
            logger.info("event=mesh_publish_denied reason=%s", decision.reason)
            return False
        env = CognitiveEventEnvelope(
            event_type=event_type,
            payload=payload,
            lane=lane,
            node_id=self.node_id,
            region=self.region,
        )
        return await self.bus.publish(env)


def build_federated_cognitive_mesh(
    db_path: Path,
    cognitive: CognitiveEditorialRuntime,
    *,
    node_id: str,
    region: str,
    federated_sync: Any | None = None,
) -> FederatedCognitiveMesh:
    repo = MeshRepository(db_path)
    bus = FederatedCognitiveBus(
        repo,
        node_id=node_id,
        region=region,
        federated_sync=federated_sync,
    )
    agents = AgentMeshRegistry(
        repo,
        cognitive.agents,
        node_id=node_id,
        region=region,
    )
    memory = FederatedCognitiveMemory(
        repo,
        cognitive.memory,
        node_id=node_id,
        region=region,
    )
    reasoning = CollectiveReasoningEngine(repo, node_id=node_id, region=region)
    learning = FederatedLearningMesh(
        repo,
        cognitive.learning,
        node_id=node_id,
        region=region,
        federated_sync=federated_sync,
    )
    resilience = CognitiveResilienceService(repo, memory, node_id=node_id)
    governance = ConstitutionalGovernance(repo)
    simulation = FederatedSimulationArena(
        repo,
        cognitive.simulation,
        governance,
        node_id=node_id,
        region=region,
    )
    economics = IntelligenceEconomics(
        repo,
        cognitive.cost,
        region=region,
        node_id=node_id,
    )
    observability = MeshObservability(repo)

    mesh = FederatedCognitiveMesh(
        repository=repo,
        bus=bus,
        agents=agents,
        memory=memory,
        reasoning=reasoning,
        learning=learning,
        resilience=resilience,
        simulation=simulation,
        economics=economics,
        governance=governance,
        observability=observability,
        cognitive=cognitive,
        node_id=node_id,
        region=region,
    )

    async def _on_evaluation(env: object) -> None:
        from bot.mesh.envelope import CognitiveEventEnvelope

        if isinstance(env, CognitiveEventEnvelope):
            logger.debug("event=mesh_received_cognitive type=%s", env.event_type)

    bus.subscribe("agent.evaluation_shared", _on_evaluation)

    logger.info(
        "event=federated_cognitive_mesh_built node_id=%s region=%s",
        node_id,
        region,
    )
    return mesh
