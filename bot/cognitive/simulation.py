from __future__ import annotations

import random
from dataclasses import dataclass

from bot.cognitive.evaluation import EvaluationPipeline
from bot.cognitive.repository import CognitiveRepository
from bot.cognitive.routing import AdaptiveModelRouter
from bot.cognitive.types import CognitiveContext, CognitivePolicyDocument, SimulationResult


@dataclass
class SimulationLane:
    name: str
    production_safe: bool


class SimulationEnvironment:
    """Isolated simulation lanes — never affects production publishing."""

    LANES = {
        "shadow": SimulationLane("shadow", True),
        "offline": SimulationLane("offline", True),
        "tournament": SimulationLane("tournament", True),
    }

    def __init__(
        self,
        repository: CognitiveRepository,
        policy: CognitivePolicyDocument,
        *,
        evaluation: EvaluationPipeline,
        router: AdaptiveModelRouter,
    ) -> None:
        self._repo = repository
        self._policy = policy
        self._evaluation = evaluation
        self._router = router

    async def run_scenario(
        self,
        scenario: str,
        *,
        lane: str = "shadow",
        seed: int = 42,
        payload: dict | None = None,
    ) -> SimulationResult:
        if lane not in self.LANES:
            lane = str(self._policy.simulation.get("default_lane", "shadow"))
        run_id = self._repo.create_simulation_run(scenario, lane=lane, seed=seed)
        rng = random.Random(seed)
        data = payload or _synthetic_payload(scenario, rng)
        scores: dict[str, float] = {}
        passed = True
        detail = ""

        if scenario == "routing_ab":
            ctx = CognitiveContext(
                importance_score=float(data.get("importance", 0.5)),
                qos_class=str(data.get("qos_class", "standard")),
                operation="summarize",
            )
            route_a = self._router.route(ctx)
            ctx_b = CognitiveContext(
                importance_score=float(data.get("importance", 0.5)) + 0.1,
                qos_class=str(data.get("qos_class", "standard")),
                operation="summarize",
            )
            route_b = self._router.route(ctx_b)
            scores["route_a_model"] = 1.0 if route_a.model else 0.0
            scores["route_b_model"] = 1.0 if route_b.model else 0.0
            scores["diversity"] = 1.0 if route_a.model != route_b.model else 0.5

        elif scenario == "policy_eval":
            results = await self._evaluation.evaluate("simulation", data)
            scores["eval_count"] = float(len(results))
            scores["avg_score"] = (
                sum(r.score for r in results) / len(results) if results else 0.0
            )
            passed = scores["avg_score"] >= 0.3

        elif scenario == "failure_injection":
            scores["resilience"] = 0.9 if data.get("recoverable") else 0.2
            passed = scores["resilience"] > 0.5

        else:
            results = await self._evaluation.evaluate("simulation", data)
            scores["composite"] = sum(r.score for r in results) / max(len(results), 1)
            passed = scores["composite"] >= float(
                self._policy.simulation.get("promotion_min_score", 0.75)
            ) * 0.5

        status = "passed" if passed else "failed"
        self._repo.complete_simulation(run_id, status=status, scores=scores)
        try:
            from bot.observability.metrics import record_simulation_run

            record_simulation_run(scenario, passed=passed)
        except Exception:
            pass
        min_promote = float(self._policy.simulation.get("promotion_min_score", 0.75))
        if passed and scores.get("composite", scores.get("avg_score", 1.0)) >= min_promote:
            detail = "eligible_for_promotion"
        return SimulationResult(run_id=run_id, scenario=scenario, passed=passed, scores=scores, detail=detail)

    async def run_tournament(
        self,
        scenarios: list[str],
        *,
        seed: int = 42,
    ) -> list[SimulationResult]:
        results = []
        for i, scenario in enumerate(scenarios):
            results.append(
                await self.run_scenario(scenario, lane="tournament", seed=seed + i)
            )
        return results


def _synthetic_payload(scenario: str, rng: random.Random) -> dict:
    return {
        "target_id": f"sim-{rng.randint(1000, 9999)}",
        "title": f"Synthetic {scenario} headline",
        "summary": "Synthetic summary for offline evaluation.",
        "priority_score": rng.uniform(0.2, 0.95),
        "source_count": rng.randint(1, 4),
        "cluster_size": rng.randint(1, 5),
        "source_trust": rng.uniform(0.3, 0.95),
        "importance": rng.uniform(0.2, 0.95),
        "qos_class": rng.choice(["breaking", "digest", "standard"]),
        "recoverable": rng.random() > 0.2,
        "item_count": rng.randint(3, 12),
    }
