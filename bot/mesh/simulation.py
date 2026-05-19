from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from bot.cognitive.simulation import SimulationEnvironment
from bot.mesh.governance import ConstitutionalGovernance
from bot.mesh.repository import MeshRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TournamentResult:
    tournament_id: str
    winner: str
    scores: dict[str, float]
    passed: bool
    detail: str


class FederatedSimulationArena:
    """Distributed simulation — never mutates production cognition."""

    def __init__(
        self,
        mesh_repo: MeshRepository,
        local_simulation: SimulationEnvironment,
        governance: ConstitutionalGovernance,
        *,
        node_id: str,
        region: str,
    ) -> None:
        self._mesh = mesh_repo
        self._local = local_simulation
        self._governance = governance
        self._node_id = node_id
        self._region = region

    async def run_tournament(
        self,
        scenarios: list[str],
        *,
        lane: str = "mesh_shadow",
        seed: int = 42,
    ) -> TournamentResult:
        tournament_id = str(uuid.uuid4())[:12]
        self._mesh.create_tournament(tournament_id, scenarios, lane=lane)

        if not self._governance.allow_simulation(lane):
            return TournamentResult(
                tournament_id=tournament_id,
                winner="none",
                scores={},
                passed=False,
                detail="simulation blocked by constitution",
            )

        if not self._mesh.spend_budget(self._region, simulation=1.0):
            return TournamentResult(
                tournament_id=tournament_id,
                winner="none",
                scores={},
                passed=False,
                detail="simulation budget exhausted",
            )

        scores: dict[str, float] = {}
        for i, scenario in enumerate(scenarios):
            result = await self._local.run_scenario(scenario, lane=lane, seed=seed + i)
            scores[scenario] = (
                result.scores.get("composite")
                or result.scores.get("avg_score")
                or (1.0 if result.passed else 0.0)
            )

        winner = max(scores, key=scores.get) if scores else "none"
        passed = all(s >= 0.5 for s in scores.values()) if scores else False
        self._mesh.complete_tournament(tournament_id, scores=scores, winner=winner)

        try:
            from bot.observability.metrics import record_mesh_tournament

            record_mesh_tournament(passed)
        except Exception:
            pass

        return TournamentResult(
            tournament_id=tournament_id,
            winner=winner,
            scores=scores,
            passed=passed,
            detail="mesh_shadow_complete",
        )

    async def agent_vs_agent(
        self,
        agent_a: str,
        agent_b: str,
        *,
        scenario: str = "policy_eval",
        seed: int = 99,
    ) -> dict[str, float]:
        r_a = await self._local.run_scenario(scenario, lane="mesh_shadow", seed=seed)
        r_b = await self._local.run_scenario(scenario, lane="mesh_shadow", seed=seed + 1)
        score_a = sum(r_a.scores.values()) / max(len(r_a.scores), 1)
        score_b = sum(r_b.scores.values()) / max(len(r_b.scores), 1)
        return {agent_a: score_a, agent_b: score_b, "winner": agent_a if score_a >= score_b else agent_b}
