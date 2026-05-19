from __future__ import annotations

from pathlib import Path

from bot.post_ga.analytics.intelligence import OperationalIntelligence
from bot.post_ga.calibration.traffic import LiveTrafficCalibrator
from bot.post_ga.coordinator import PostGaCoordinator
from bot.post_ga.governance.evolution import PostLaunchGovernance
from bot.post_ga.operator.load import OperatorLoadManager
from bot.post_ga.optimization.proposals import SafeSelfOptimizer
from bot.post_ga.quality.learning import ProductionQualityLearner
from bot.post_ga.repository import PostGaRepository
from bot.post_ga.risk.prediction import LiveRiskPredictor
from bot.post_ga.settings import PostGaSettings
from bot.post_ga.stability.autonomy import AutonomyStabilizer
from bot.post_ga.telemetry.executive import LiveExecutiveTelemetry


def build_post_ga_stack(db_path: Path) -> PostGaCoordinator:
    settings = PostGaSettings.from_env()
    repo = PostGaRepository(db_path)
    return PostGaCoordinator(
        settings=settings,
        repository=repo,
        calibration=LiveTrafficCalibrator(repo),
        quality=ProductionQualityLearner(repo),
        autonomy=AutonomyStabilizer(repo),
        operator_load=OperatorLoadManager(),
        analytics=OperationalIntelligence(),
        risk=LiveRiskPredictor(repo),
        optimizer=SafeSelfOptimizer(repo, auto_threshold=settings.optimization_auto_threshold),
        governance=PostLaunchGovernance(repo),
        exec_telemetry=LiveExecutiveTelemetry(),
    )
