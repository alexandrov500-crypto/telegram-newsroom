from __future__ import annotations

from pathlib import Path

from bot.ga_ops.automation.advisor import OpsAdvisor
from bot.ga_ops.coordinator import GaOpsCoordinator
from bot.ga_ops.feedback.loop import ProductionFeedbackLoop
from bot.ga_ops.lifecycle.retention import DataLifecycleManager
from bot.ga_ops.quality.validator import AiQualityValidator
from bot.ga_ops.readiness.evaluator import GaReadinessEvaluator
from bot.ga_ops.repository import GaOpsRepository
from bot.ga_ops.rollback.safety import RollbackSafetyManager
from bot.ga_ops.scaling.readiness import ScalingReadinessEvaluator
from bot.ga_ops.settings import GaOpsSettings
from bot.ga_ops.reporting.summary import ProductionSummaryBuilder
from bot.ga_ops.traffic.guardrails import PublicTrafficGuardrails


def build_ga_ops_stack(db_path: Path) -> GaOpsCoordinator:
    settings = GaOpsSettings.from_env()
    repo = GaOpsRepository(db_path)
    return GaOpsCoordinator(
        settings=settings,
        repository=repo,
        traffic=PublicTrafficGuardrails(
            repo,
            max_publishes_per_hour=settings.max_publishes_per_hour,
            surge_queue_threshold=settings.surge_queue_threshold,
        ),
        quality=AiQualityValidator(repo),
        feedback=ProductionFeedbackLoop(repo),
        lifecycle=DataLifecycleManager(repo),
        advisor=OpsAdvisor(),
        scaling=ScalingReadinessEvaluator(),
        rollback=RollbackSafetyManager(repo),
        readiness=GaReadinessEvaluator(min_score=settings.ga_readiness_min_score),
        summary=ProductionSummaryBuilder(),
    )
