from __future__ import annotations

from dataclasses import dataclass

from bot.cognitive.cost import CostIntelligence
from bot.mesh.repository import MeshRepository


@dataclass(frozen=True)
class MeshResourceDecision:
    allow: bool
    reasoning_depth: str
    agent_slots: int
    memory_replicas: int
    reason: str


class IntelligenceEconomics:
    """Distributed cognitive resource governance."""

    def __init__(
        self,
        mesh_repo: MeshRepository,
        local_cost: CostIntelligence,
        *,
        region: str,
        node_id: str,
    ) -> None:
        self._mesh = mesh_repo
        self._local = local_cost
        self._region = region
        self._node_id = node_id

    def decide(
        self,
        *,
        mesh_pressure: float = 0.0,
        cross_region_bandwidth: float = 1.0,
        importance: float = 0.5,
    ) -> MeshResourceDecision:
        budget = self._mesh.get_budget(self._region)
        reasoning_headroom = float(budget.get("reasoning_quota", 100)) - float(
            budget.get("spent_reasoning", 0)
        )
        if reasoning_headroom <= 0 or mesh_pressure > 0.9:
            return MeshResourceDecision(
                allow=False,
                reasoning_depth="none",
                agent_slots=0,
                memory_replicas=0,
                reason="regional_quota_or_pressure",
            )
        depth = "deep" if importance > 0.8 and mesh_pressure < 0.5 else "medium"
        if mesh_pressure > 0.7:
            depth = "shallow"
        replicas = 2 if cross_region_bandwidth > 0.5 and importance > 0.6 else 1
        slots = max(1, int(3 * (1.0 - mesh_pressure)))
        return MeshResourceDecision(
            allow=True,
            reasoning_depth=depth,
            agent_slots=slots,
            memory_replicas=replicas,
            reason=f"pressure={mesh_pressure:.2f} importance={importance:.2f}",
        )

    def record_usage(
        self,
        *,
        reasoning: float = 0,
        memory: float = 0,
        simulation: float = 0,
    ) -> bool:
        ok = self._mesh.spend_budget(
            self._region,
            reasoning=reasoning,
            memory=memory,
            simulation=simulation,
        )
        if reasoning > 0:
            self._local.record_spend(reasoning * 0.001)
        return ok

    def balance_pressure(self, regional_pressures: dict[str, float]) -> dict[str, str]:
        """Recommend load shift from hot regions."""
        if not regional_pressures:
            return {}
        avg = sum(regional_pressures.values()) / len(regional_pressures)
        actions: dict[str, str] = {}
        for region, pressure in regional_pressures.items():
            if pressure > avg + 0.2:
                actions[region] = "shed_cognition"
            elif pressure < avg - 0.2:
                actions[region] = "accept_overflow"
        return actions

    def forecast_mesh_cost(self, *, hourly_reasoning_units: float, hours: int = 8) -> float:
        budget = self._mesh.get_budget(self._region)
        projected = float(budget.get("spent_reasoning", 0)) + hourly_reasoning_units * hours
        return round(projected, 2)
