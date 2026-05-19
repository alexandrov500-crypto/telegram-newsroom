from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from bot.ga_ops.automation.advisor import OpsAdvisor
from bot.ga_ops.feedback.loop import ProductionFeedbackLoop
from bot.ga_ops.lifecycle.retention import DataLifecycleManager
from bot.ga_ops.quality.validator import AiQualityValidator, QualityVerdict
from bot.ga_ops.readiness.evaluator import GaReadinessEvaluator, GaReadinessResult
from bot.ga_ops.repository import GaOpsRepository
from bot.ga_ops.rollback.safety import RollbackSafetyManager
from bot.ga_ops.scaling.readiness import ScalingReadinessEvaluator
from bot.ga_ops.settings import GaOpsSettings
from bot.ga_ops.reporting.summary import ProductionSummaryBuilder
from bot.ga_ops.traffic.guardrails import PublicTrafficGuardrails, PublishGuardrailVerdict

logger = logging.getLogger(__name__)


@dataclass
class GaOpsCoordinator:
    settings: GaOpsSettings
    repository: GaOpsRepository
    traffic: PublicTrafficGuardrails
    quality: AiQualityValidator
    feedback: ProductionFeedbackLoop
    lifecycle: DataLifecycleManager
    advisor: OpsAdvisor
    scaling: ScalingReadinessEvaluator
    rollback: RollbackSafetyManager
    readiness: GaReadinessEvaluator
    summary: ProductionSummaryBuilder
    _signals_fn: Callable[[], dict[str, Any]] | None = None
    _last_ga: GaReadinessResult | None = None
    _tick: int = 0

    def configure_signals(self, fn: Callable[[], dict[str, Any]]) -> None:
        self._signals_fn = fn

    async def startup(self) -> None:
        self.rollback.create_snapshot(
            stage="startup",
            detail={"build": "ga_ops", "republish_blocked": True},
        )
        logger.info("event=ga_ops_installed")

    def check_publish(
        self,
        *,
        queue_depth: int = 0,
        trust_score: float = 0.85,
        narrative_key: str | None = None,
        language: str = "en",
        breaking_news: bool = False,
    ) -> PublishGuardrailVerdict:
        if not self.settings.traffic_guardrails:
            from bot.ga_ops.traffic.guardrails import TrafficPressure

            return PublishGuardrailVerdict(
                allowed=True,
                pressure=TrafficPressure.PUBLIC_TRAFFIC_SAFE,
                reason="guardrails_off",
                max_rate_per_hour=self.settings.max_publishes_per_hour,
            )
        return self.traffic.evaluate(
            queue_depth=queue_depth,
            trust_score=trust_score,
            narrative_key=narrative_key,
            language=language,
            breaking_news=breaking_news,
        )

    def validate_quality(
        self,
        *,
        headline: str,
        summary: str,
        story_id: int | None = None,
        pending_news_id: int | None = None,
        contradiction_score: float = 0.0,
    ) -> QualityVerdict:
        if not self.settings.quality_validation:
            return QualityVerdict(
                overall=1.0,
                headline=1.0,
                consistency=1.0,
                contradiction=0.0,
                toxicity=0.0,
                readability=1.0,
                passed=True,
                blockers=(),
            )
        return self.quality.evaluate(
            headline=headline,
            summary=summary,
            story_id=story_id,
            pending_news_id=pending_news_id,
            contradiction_score=contradiction_score,
        )

    async def tick(self, signals: dict[str, Any] | None = None) -> dict[str, Any]:
        self._tick += 1
        sig = signals or (self._signals_fn() if self._signals_fn else {})
        queue = int(sig.get("queue_depth", 0))
        scaling = self.scaling.evaluate(
            queue_depth=queue,
            worker_stale=int(sig.get("worker_stale", 0)),
            worker_total=int(sig.get("worker_total", 0)),
            publishes_hour=len(self.traffic._publish_timestamps),
            max_publish_hour=self.settings.max_publishes_per_hour,
            redis_enabled=bool(sig.get("redis_enabled", False)),
            event_bus_pending=int(sig.get("event_bus_pending", 0)),
        )
        self._last_ga = self.readiness.evaluate(
            uptime_stable=bool(sig.get("uptime_ok", True)),
            slo_violations=int(sig.get("slo_violations", 0)),
            critical_incidents=int(sig.get("critical_incidents", 0)),
            confidence_trend=float(sig.get("go_live_confidence", 0)),
            quality_avg=self.quality.trend_avg(),
            publish_integrity=float(sig.get("publish_integrity", 1.0)),
            operator_responsive=True,
            scaling_risk=float(scaling["scaling_risk_score"]),
            rollback_ready=self.repository.latest_rollback_snapshot() is not None,
            certification_state=str(sig.get("certification_state", "NOT_READY")),
        )
        self.repository.set_ga_readiness(
            state=self._last_ga.state.value,
            score=self._last_ga.score,
            blockers=list(self._last_ga.blockers),
        )
        if self.settings.retention_enabled and self._tick % 96 == 0:
            self.lifecycle.run_maintenance()
        return {
            "ga_readiness": self._last_ga.state.value,
            "ga_score": self._last_ga.score,
            "traffic": self.traffic.snapshot(),
            "scaling": scaling,
            "quality_avg": self.quality.trend_avg(),
        }

    def evaluate_ga(self) -> GaReadinessResult:
        sig = self._signals_fn() if self._signals_fn else {}
        self._last_ga = self.readiness.evaluate(
            uptime_stable=bool(sig.get("uptime_ok", True)),
            slo_violations=int(sig.get("slo_violations", 0)),
            critical_incidents=int(sig.get("critical_incidents", 0)),
            confidence_trend=float(sig.get("go_live_confidence", 0)),
            quality_avg=self.quality.trend_avg(),
            publish_integrity=float(sig.get("publish_integrity", 1.0)),
            scaling_risk=float(sig.get("scaling_risk", 0)),
            certification_state=str(sig.get("certification_state", "NOT_READY")),
        )
        return self._last_ga

    def production_summary_text(self) -> str:
        sig = self._signals_fn() if self._signals_fn else {}
        ga = self._last_ga or self.evaluate_ga()
        traffic = self.traffic.snapshot()
        return self.summary.build(
            ga=ga,
            publish_health=float(sig.get("publish_integrity", 1.0)),
            operational_risk=float(sig.get("operational_risk", 0.2)),
            quality_trend=self.quality.trend_avg(),
            ai_spend_usd=float(sig.get("ai_spend_usd", 0)),
            scaling_risk=float(sig.get("scaling_risk", 0)),
            active_incidents=int(sig.get("critical_incidents", 0)),
            certification_state=str(sig.get("certification_state", "NOT_READY")),
            traffic_pressure=str(traffic.get("pressure", "PUBLIC_TRAFFIC_SAFE")),
        )
