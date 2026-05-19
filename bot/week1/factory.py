from __future__ import annotations

from pathlib import Path

from bot.week1.alerts.noise_reduction import AlertNoiseReducer
from bot.week1.baseline.capture import ProductionBaselineCapture
from bot.week1.coordinator import Week1Coordinator
from bot.week1.copilot.assistant import Week1OpsCopilot
from bot.week1.optimization.recommendations import SafeAdaptiveOptimization
from bot.week1.quality.tuning import PublicationQualityTuner
from bot.week1.reporting.executive import Week1ExecutiveReporting
from bot.week1.repository import Week1Repository
from bot.week1.risk.stabilization import RiskStabilization
from bot.week1.settings import Week1Settings
from bot.week1.survivability.scoring import SurvivabilityScoring
from bot.week1.traffic.adaptation import LiveTrafficAdapter


def build_week1_stack(db_path: Path) -> Week1Coordinator:
    settings = Week1Settings.from_env()
    repo = Week1Repository(db_path)
    return Week1Coordinator(
        settings=settings,
        repository=repo,
        alerts=AlertNoiseReducer(
            repo,
            dedupe_sec=settings.alert_dedupe_sec,
            actionable_only=settings.actionable_only,
        ),
        quality=PublicationQualityTuner(repo),
        copilot=Week1OpsCopilot(repo),
        traffic=LiveTrafficAdapter(),
        risk=RiskStabilization(repo),
        reporting=Week1ExecutiveReporting(repo),
        baseline=ProductionBaselineCapture(repo),
        optimization=SafeAdaptiveOptimization(repo),
        survivability=SurvivabilityScoring(repo),
    )
