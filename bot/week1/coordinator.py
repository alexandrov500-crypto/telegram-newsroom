from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from bot.week1.alerts.noise_reduction import AlertNoiseReducer
from bot.week1.baseline.capture import ProductionBaselineCapture
from bot.week1.copilot.assistant import Week1OpsCopilot
from bot.week1.optimization.recommendations import SafeAdaptiveOptimization
from bot.week1.quality.tuning import PublicationQualityTuner
from bot.week1.reporting.executive import Week1ExecutiveReporting
from bot.week1.repository import Week1Repository
from bot.week1.risk.stabilization import RiskStabilization
from bot.week1.settings import Week1Settings
from bot.week1.survivability.scoring import SurvivabilityScoring
from bot.week1.traffic.adaptation import LiveTrafficAdapter

logger = logging.getLogger(__name__)


@dataclass
class Week1Coordinator:
    settings: Week1Settings
    repository: Week1Repository
    alerts: AlertNoiseReducer
    quality: PublicationQualityTuner
    copilot: Week1OpsCopilot
    traffic: LiveTrafficAdapter
    risk: RiskStabilization
    reporting: Week1ExecutiveReporting
    baseline: ProductionBaselineCapture
    optimization: SafeAdaptiveOptimization
    survivability: SurvivabilityScoring
    _signals_fn: Callable[[], dict[str, Any]] | None = None
    _tick: int = 0
    _stable_ticks: int = 0

    def configure_signals(self, fn: Callable[[], dict[str, Any]]) -> None:
        self._signals_fn = fn

    async def startup(self) -> None:
        from bot.ops_playbook.settings import OpsPlaybookSettings

        self.repository.init_state(week_start_at=OpsPlaybookSettings.default_production_start())
        logger.info("event=week1_stabilization_installed")

    async def tick(self, signals: dict[str, Any] | None = None) -> dict[str, Any]:
        self._tick += 1
        sig = dict(signals or (self._signals_fn() if self._signals_fn else {}))

        risk = self.risk.score(sig)
        sig.update(risk)
        traffic = self.traffic.score(sig)
        sig.update(traffic)
        quality_detail = self.quality.observe(sig)
        surv = self.survivability.compute(sig)

        if (
            self.settings.baseline_auto_capture
            and not (self.repository.get_state() or {}).get("baseline_captured")
            and risk["stabilization_risk"] < 0.35
            and int(sig.get("queue_depth", 999)) < 120
        ):
            self._stable_ticks += 1
            if self._stable_ticks >= 12:
                self.baseline.capture_all(sig)
        else:
            self._stable_ticks = max(0, self._stable_ticks - 1)

        if self._tick % 48 == 0:
            self.optimization.propose_from_signals(sig)

        return {
            "stabilization_risk": risk["stabilization_risk"],
            "rollback_probability": risk["rollback_probability"],
            "survivability_score": surv["survivability_score"],
            "noise_index": self.alerts.noise_index(),
            "baseline_captured": bool(
                (self.repository.get_state() or {}).get("baseline_captured"),
            ),
        }

    def should_surface_alert(
        self,
        *,
        title: str,
        severity: str,
        symptoms: list[str] | None = None,
        subsystem: str | None = None,
    ) -> bool:
        return self.alerts.evaluate(
            title=title,
            severity=severity,
            symptoms=symptoms,
            subsystem=subsystem,
        ).surface
