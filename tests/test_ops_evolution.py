from __future__ import annotations

from pathlib import Path

import pytest

from bot.ops_evolution.assistant.knowledge import OperatorKnowledgeAssistant
from bot.ops_evolution.maturity.model import PlatformMaturityModel
from bot.ops_evolution.memory.operational import OperationalMemorySystem
from bot.ops_evolution.repository import OpsEvolutionRepository
from bot.ops_evolution.safety.evolution import EvolutionSafetyLayer
from bot.ops_evolution.strategy.engine import StrategicOptimizationEngine
from bot.storage.db import init_database


@pytest.fixture
def repo(tmp_path: Path) -> OpsEvolutionRepository:
    init_database(tmp_path / "evo.db")
    return OpsEvolutionRepository(tmp_path / "evo.db")


def test_memory_and_patterns(repo: OpsEvolutionRepository) -> None:
    mem = OperationalMemorySystem(repo)
    for _ in range(4):
        mem.remember_incident(incident_key="queue_spike", summary="queue high", outcome="open")
    mem.remember_recovery(incident_key="queue_spike", success=True, remediation="throttle ingest")
    patterns = repo.recurring_patterns(min_count=3)
    assert len(patterns) >= 1


def test_strategy_proposal(repo: OpsEvolutionRepository) -> None:
    engine = StrategicOptimizationEngine(repo)
    ids = engine.analyze_signals({"queue_depth": 500, "quality_avg": 0.6})
    assert len(ids) >= 1
    assert len(repo.pending_strategies()) >= 1


def test_maturity_scoring_with_db(repo: OpsEvolutionRepository) -> None:
    m = PlatformMaturityModel(repo)
    s = m.score(
        {
            "uptime_score": 0.9,
            "trust_score": 0.85,
            "scaling_risk": 0.1,
            "ga_score": 0.88,
            "recovery_ok": 1.0,
            "quality_avg": 0.8,
            "autonomy_score": 0.85,
        },
    )
    assert s["overall"] > 0.7


def test_evolution_safety_flags(repo: OpsEvolutionRepository) -> None:
    layer = EvolutionSafetyLayer(repo)
    r = layer.evaluate(
        signals={
            "operator_attention": 0.3,
            "optimization_count": 15,
            "trust_score": 0.99,
        },
    )
    assert r["evolution_risk"] > 0
    assert "operator_disengagement" in r["flags"]


def test_assistant_grounded(repo: OpsEvolutionRepository) -> None:
    mem = OperationalMemorySystem(repo)
    mem.remember_incident(incident_key="dlq", summary="DLQ explosion", outcome="resolved")
    ast = OperatorKnowledgeAssistant(repo, mem)
    text = ast.answer("explain incidents")
    assert "internal" in text.lower() or "DLQ" in text
