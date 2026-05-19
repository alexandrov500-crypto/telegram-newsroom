from __future__ import annotations

import logging
from dataclasses import dataclass

from bot.mesh.memory import FederatedCognitiveMemory
from bot.mesh.repository import MeshRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CognitiveHealthReport:
    mesh_health: float
    trust_decay: float
    quarantined_nodes: tuple[str, ...]
    stale_evaluations: int
    memory_desync: int
    recommendations: tuple[str, ...]


class CognitiveResilienceService:
    """Graceful degradation under cognitive uncertainty."""

    def __init__(
        self,
        repository: MeshRepository,
        memory: FederatedCognitiveMemory | None = None,
        *,
        node_id: str,
    ) -> None:
        self._repo = repository
        self._memory = memory
        self._node_id = node_id

    def assess(
        self,
        *,
        stale_eval_count: int = 0,
        memory_ids_checked: list[str] | None = None,
        failed_nodes: list[str] | None = None,
    ) -> CognitiveHealthReport:
        state = self._repo.get_resilience()
        desync = 0
        for mid in memory_ids_checked or []:
            if self._memory:
                rec = self._memory.reconcile(mid)
                if rec.get("status") == "divergent":
                    desync += 1

        health = float(state["mesh_health"])
        health -= stale_eval_count * 0.02
        health -= desync * 0.05
        if failed_nodes:
            health -= len(failed_nodes) * 0.03
        health = max(0.0, min(1.0, health))

        trust_decay = min(1.0, float(state["trust_decay"]) + stale_eval_count * 0.01)
        quarantined = list(state["quarantined_nodes"])
        for node in failed_nodes or []:
            if node not in quarantined and health < 0.5:
                quarantined.append(node)

        recommendations: list[str] = []
        if health < 0.6:
            recommendations.append("reduce_cognition_depth")
        if desync > 0:
            recommendations.append("run_memory_reconciliation")
        if stale_eval_count > 5:
            recommendations.append("quarantine_stale_evaluations")
        if trust_decay > 0.3:
            recommendations.append("confidence_degradation_mode")

        self._repo.update_resilience(
            mesh_health=health,
            trust_decay=trust_decay,
            quarantined_nodes=quarantined[:20],
        )
        return CognitiveHealthReport(
            mesh_health=round(health, 4),
            trust_decay=round(trust_decay, 4),
            quarantined_nodes=tuple(quarantined),
            stale_evaluations=stale_eval_count,
            memory_desync=desync,
            recommendations=tuple(recommendations),
        )

    def quarantine_node(self, node_id: str, *, reason: str) -> None:
        state = self._repo.get_resilience()
        nodes = list(state["quarantined_nodes"])
        if node_id not in nodes:
            nodes.append(node_id)
        self._repo.update_resilience(quarantined_nodes=nodes)
        logger.warning("event=cognitive_quarantine node=%s reason=%s", node_id, reason)

    def repair_memory(self, memory_id: str, *, prefer_region: str) -> bool:
        if self._memory is None:
            return False
        return self._memory.rollback_memory(memory_id, to_region=prefer_region)

    def is_quarantined(self, node_id: str) -> bool:
        return node_id in self._repo.get_resilience()["quarantined_nodes"]
