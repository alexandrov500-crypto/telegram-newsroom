from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EvaluationDimension:
    name: str
    score: float
    weight: float = 1.0
    explanation: str = ""


@dataclass
class EvaluationResult:
    evaluation_id: str
    target_type: str
    target_id: str
    evaluator_name: str
    score: float
    dimensions: list[EvaluationDimension]
    explanation: str
    trace_id: str | None = None
    replay_key: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "evaluation_id": self.evaluation_id,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "evaluator_name": self.evaluator_name,
            "score": self.score,
            "dimensions": [
                {
                    "name": d.name,
                    "score": d.score,
                    "weight": d.weight,
                    "explanation": d.explanation,
                }
                for d in self.dimensions
            ],
            "explanation": self.explanation,
            "trace_id": self.trace_id,
            "replay_key": self.replay_key,
        }


@dataclass(frozen=True)
class RouteDecision:
    route_id: str
    model: str
    strategy: str
    context_tokens: int
    generation_depth: str
    reasoning_mode: str
    language_path: str
    fallback_chain: tuple[str, ...]
    reason: str
    estimated_cost_usd: float = 0.0


@dataclass
class CognitiveContext:
    """Runtime signals for cognitive decisions."""

    importance_score: float = 0.5
    qos_class: str = "standard"
    latency_pressure: float = 0.0
    degradation_mode: str = "normal"
    node_load: float = 0.0
    historical_quality: float = 0.7
    story_id: int | None = None
    pending_news_id: int | None = None
    region: str = "global"
    operation: str = "summarize"
    source_count: int = 1
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Prediction:
    forecast_type: str
    horizon_minutes: int
    predicted_value: float
    confidence: float
    explanation: str


@dataclass(frozen=True)
class SimulationResult:
    run_id: str
    scenario: str
    passed: bool
    scores: dict[str, float]
    detail: str


@dataclass(frozen=True)
class AgentSpec:
    agent_id: str
    name: str
    capabilities: tuple[str, ...]
    autonomy_bound: int = 1


@dataclass
class CognitivePolicyDocument:
    policy_id: str
    version: int
    evaluation_enabled: bool = True
    max_evaluations_per_hour: int = 500
    routing: dict[str, Any] = field(default_factory=dict)
    learning: dict[str, Any] = field(default_factory=dict)
    cost: dict[str, Any] = field(default_factory=dict)
    simulation: dict[str, Any] = field(default_factory=dict)
    memory: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "version": self.version,
            "evaluation_enabled": self.evaluation_enabled,
            "max_evaluations_per_hour": self.max_evaluations_per_hour,
            "routing": self.routing,
            "learning": self.learning,
            "cost": self.cost,
            "simulation": self.simulation,
            "memory": self.memory,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CognitivePolicyDocument:
        return cls(
            policy_id=str(data.get("policy_id", "cognitive_default")),
            version=int(data.get("version", 1)),
            evaluation_enabled=bool(data.get("evaluation_enabled", True)),
            max_evaluations_per_hour=int(data.get("max_evaluations_per_hour", 500)),
            routing=dict(data.get("routing") or {}),
            learning=dict(data.get("learning") or {}),
            cost=dict(data.get("cost") or {}),
            simulation=dict(data.get("simulation") or {}),
            memory=dict(data.get("memory") or {}),
        )
