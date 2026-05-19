from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from bot.ops_evolution.analytics.long_horizon import LongHorizonAnalytics
from bot.ops_evolution.assistant.knowledge import OperatorKnowledgeAssistant
from bot.ops_evolution.cognition.governance import AdaptiveCognitionGovernance
from bot.ops_evolution.maintenance.orchestrator import MaintenanceOrchestrator
from bot.ops_evolution.maturity.model import PlatformMaturityModel
from bot.ops_evolution.memory.operational import OperationalMemorySystem
from bot.ops_evolution.reporting.executive import EvolutionExecutiveReport
from bot.ops_evolution.repository import OpsEvolutionRepository
from bot.ops_evolution.safety.evolution import EvolutionSafetyLayer
from bot.ops_evolution.settings import OpsEvolutionSettings
from bot.ops_evolution.strategy.engine import StrategicOptimizationEngine

logger = logging.getLogger(__name__)


@dataclass
class OpsEvolutionCoordinator:
    settings: OpsEvolutionSettings
    repository: OpsEvolutionRepository
    memory: OperationalMemorySystem
    strategy: StrategicOptimizationEngine
    cognition: AdaptiveCognitionGovernance
    assistant: OperatorKnowledgeAssistant
    analytics: LongHorizonAnalytics
    maintenance: MaintenanceOrchestrator
    maturity: PlatformMaturityModel
    safety: EvolutionSafetyLayer
    reporting: EvolutionExecutiveReport
    _signals_fn: Callable[[], dict[str, Any]] | None = None
    _last_maturity: dict[str, float] | None = None
    _last_safety: dict[str, Any] | None = None
    _tick: int = 0

    def configure_signals(self, fn: Callable[[], dict[str, Any]]) -> None:
        self._signals_fn = fn

    async def startup(self) -> None:
        self.memory.remember_operator_outcome(
            action="ops_evolution_startup",
            success=True,
            detail={"phase": "long_term_evolution"},
        )
        logger.info("event=ops_evolution_installed")

    async def tick(self, signals: dict[str, Any] | None = None) -> dict[str, Any]:
        self._tick += 1
        sig = signals or (self._signals_fn() if self._signals_fn else {})

        self.analytics.ingest_tick(signals=sig)
        if self._tick % 336 == 0:
            self.analytics.flush_weekly_if_due()
            self.repository.archive_old_memories()

        if self.settings.strategy and self._tick % 24 == 0:
            self.strategy.analyze_signals(sig)

        if sig.get("failure_issues"):
            for issue in sig["failure_issues"][:3]:
                self.memory.remember_incident(
                    incident_key=issue.get("id", "unknown"),
                    summary=str(issue.get("id", "")),
                    outcome="detected",
                )

        maturity = {}
        if self.settings.maturity_model:
            maturity = self.maturity.score(sig)
            self._last_maturity = maturity

        safety = {}
        if self.settings.evolution_safety:
            safety = self.safety.evaluate(signals=sig)
            self._last_safety = safety

        if self.settings.maintenance_orchestration and self._tick % 48 == 0:
            self.maintenance.propose_plan(signals=sig)

        return {
            "maturity_overall": maturity.get("overall", 0),
            "evolution_risk": safety.get("evolution_risk", 0),
            "strategic_pending": len(self.repository.pending_strategies()),
        }

    def evolution_report_text(self) -> str:
        sig = self._signals_fn() if self._signals_fn else {}
        m = self._last_maturity or self.maturity.score(sig)
        overall = m.get("overall", 0.0)
        weakest = min(
            ((k, v) for k, v in m.items() if k != "overall"),
            key=lambda x: x[1],
            default=("n/a", 0),
        )[0]
        safety = self._last_safety or {}
        return self.reporting.build(
            maturity_overall=overall,
            sustainability=float(sig.get("quality_avg", 0.8)),
            trust_trend=str(sig.get("trust_trend", "stable")),
            evolution_risk=float(safety.get("evolution_risk", 0)),
            autonomy_score=float(sig.get("autonomy_score", 0.8)),
            operator_attention=float(sig.get("operator_attention", 1.0)),
            strategic_pending=len(self.repository.pending_strategies()),
            weakest_domain=weakest,
            long_term_risks=list(safety.get("flags", [])),
        )
