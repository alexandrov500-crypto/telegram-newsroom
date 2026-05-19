from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from bot.post_ga.analytics.intelligence import OperationalIntelligence
from bot.post_ga.calibration.traffic import LiveTrafficCalibrator
from bot.post_ga.governance.evolution import PostLaunchGovernance
from bot.post_ga.operator.load import OperatorLoadManager
from bot.post_ga.optimization.proposals import SafeSelfOptimizer
from bot.post_ga.quality.learning import ProductionQualityLearner
from bot.post_ga.repository import PostGaRepository
from bot.post_ga.risk.prediction import LiveRiskPredictor
from bot.post_ga.settings import PostGaSettings
from bot.post_ga.stability.autonomy import AutonomyStabilizer
from bot.post_ga.telemetry.executive import LiveExecutiveTelemetry

logger = logging.getLogger(__name__)


@dataclass
class PostGaCoordinator:
    settings: PostGaSettings
    repository: PostGaRepository
    calibration: LiveTrafficCalibrator
    quality: ProductionQualityLearner
    autonomy: AutonomyStabilizer
    operator_load: OperatorLoadManager
    analytics: OperationalIntelligence
    risk: LiveRiskPredictor
    optimizer: SafeSelfOptimizer
    governance: PostLaunchGovernance
    exec_telemetry: LiveExecutiveTelemetry
    _signals_fn: Callable[[], dict[str, Any]] | None = None
    _last_forecast: dict[str, Any] | None = None
    _tick: int = 0

    def configure_signals(self, fn: Callable[[], dict[str, Any]]) -> None:
        self._signals_fn = fn

    async def startup(self) -> None:
        logger.info("event=post_ga_installed")

    async def tick(self, signals: dict[str, Any] | None = None) -> dict[str, Any]:
        self._tick += 1
        sig = signals or (self._signals_fn() if self._signals_fn else {})
        queue = int(sig.get("queue_depth", 0))

        cal = {}
        if self.settings.calibration:
            cal = self.calibration.calibrate(
                queue_depth=queue,
                trust_score=float(sig.get("trust_score", 0.85)),
            )

        stab = {}
        if self.settings.autonomy_stabilization:
            stab = self.autonomy.observe(
                queue_depth=queue,
                retry_count=int(sig.get("retry_rate", 0)),
                memory_mb=float(sig.get("memory_mb", 0)),
                task_count=int(sig.get("task_count", 0)),
            )

        forecast = {}
        if self.settings.risk_prediction:
            forecast = self.risk.forecast(
                queue_depth=queue,
                queue_growth=float(sig.get("queue_growth", 0)),
                slo_burn=float(sig.get("slo_burn", 0)),
                operator_attention=self.operator_load.attention_score,
                floodwait_recent=int(sig.get("floodwait_hour", 0)),
                spend_hour=float(sig.get("budget_hour", 0)),
                quality_confidence=self.quality.quality_confidence,
                trust_score=float(sig.get("trust_score", 0.85)),
            )
            self._last_forecast = forecast

        self.governance.record_trust(float(sig.get("trust_score", 0.85)))

        for issue in sig.get("failure_issues", [])[:5]:
            self.operator_load.ingest_alert(
                issue.get("id", "unknown"),
                severity=issue.get("severity", "warn"),
                title=issue.get("id", "issue"),
                remediation=issue.get("remediation", "/ops_advisor"),
                importance=0.7 if issue.get("severity") == "critical" else 0.4,
            )

        if self.settings.self_optimization and self._tick % 12 == 0:
            self.optimizer.generate_from_signals(
                {**sig, "pacing_factor": cal.get("pacing", {}).get("factor", 1.0)},
            )

        return {
            "calibration": cal,
            "stability": stab,
            "risk": forecast,
            "quality_confidence": self.quality.quality_confidence,
        }

    def live_exec_text(self) -> str:
        sig = self._signals_fn() if self._signals_fn else {}
        cal = self.repository.get_calibration() or {}
        stab = self.repository.get_stability() or {}
        fc = self._last_forecast or {}
        return self.exec_telemetry.build(
            audience=float(cal.get("audience_responsiveness", 0.5)),
            publish_efficiency=float(cal.get("publish_efficiency", 0.5)),
            autonomy_score=float(stab.get("autonomy_score", 0.8)),
            risk_top=str(fc.get("top_risk", "none")),
            risk_prob=float(fc.get("top_probability", 0)),
            quality_confidence=self.quality.quality_confidence,
            trust_trend=self.governance.trust_trend(),
            operator_attention=self.operator_load.attention_score,
            scaling_risk=float(sig.get("scaling_risk", 0)),
            ga_confidence=float(sig.get("go_live_confidence", 0)),
        )

    def recommended_pacing_factor(self) -> float:
        return self.calibration.recommended_pacing_factor
