from __future__ import annotations

from pathlib import Path

from bot.ops_evolution.analytics.long_horizon import LongHorizonAnalytics
from bot.ops_evolution.assistant.knowledge import OperatorKnowledgeAssistant
from bot.ops_evolution.cognition.governance import AdaptiveCognitionGovernance
from bot.ops_evolution.coordinator import OpsEvolutionCoordinator
from bot.ops_evolution.maintenance.orchestrator import MaintenanceOrchestrator
from bot.ops_evolution.maturity.model import PlatformMaturityModel
from bot.ops_evolution.memory.operational import OperationalMemorySystem
from bot.ops_evolution.reporting.executive import EvolutionExecutiveReport
from bot.ops_evolution.repository import OpsEvolutionRepository
from bot.ops_evolution.safety.evolution import EvolutionSafetyLayer
from bot.ops_evolution.settings import OpsEvolutionSettings
from bot.ops_evolution.strategy.engine import StrategicOptimizationEngine


def build_ops_evolution_stack(db_path: Path) -> OpsEvolutionCoordinator:
    settings = OpsEvolutionSettings.from_env()
    repo = OpsEvolutionRepository(db_path)
    memory = OperationalMemorySystem(repo)
    return OpsEvolutionCoordinator(
        settings=settings,
        repository=repo,
        memory=memory,
        strategy=StrategicOptimizationEngine(repo),
        cognition=AdaptiveCognitionGovernance(),
        assistant=OperatorKnowledgeAssistant(repo, memory),
        analytics=LongHorizonAnalytics(repo),
        maintenance=MaintenanceOrchestrator(repo),
        maturity=PlatformMaturityModel(repo),
        safety=EvolutionSafetyLayer(repo),
        reporting=EvolutionExecutiveReport(),
    )
