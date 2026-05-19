from __future__ import annotations

from pathlib import Path

from bot.operational_memory.coordinator import OperationalMemoryCoordinator
from bot.operational_memory.drift.monitor import DriftMonitor
from bot.operational_memory.fingerprints.engine import FingerprintEngine
from bot.operational_memory.learning.outcomes import OutcomeLearner
from bot.operational_memory.memory_store.incidents import IncidentMemoryStore
from bot.operational_memory.prediction.engine import PredictiveRiskEngine
from bot.operational_memory.recommendations.v2 import OperationalRecommendationsV2
from bot.operational_memory.repository import OperationalMemoryRepository
from bot.operational_memory.seasonality.calendar import SeasonalityCalendar
from bot.operational_memory.settings import OperationalMemorySettings


def build_opmem_stack(db_path: Path) -> OperationalMemoryCoordinator:
    settings = OperationalMemorySettings.from_env()
    repo = OperationalMemoryRepository(db_path)
    return OperationalMemoryCoordinator(
        settings=settings,
        repository=repo,
        incidents=IncidentMemoryStore(repo),
        fingerprints=FingerprintEngine(repo),
        prediction=PredictiveRiskEngine(repo),
        drift=DriftMonitor(repo),
        seasonality=SeasonalityCalendar(repo),
        recommendations=OperationalRecommendationsV2(repo),
        outcomes=OutcomeLearner(repo),
    )
