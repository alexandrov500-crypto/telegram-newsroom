from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from bot.operations.certification import ProductionReadinessCertification
from bot.operations.repository import OperationsRepository
from bot.operations.types import ProductionSLOs


@dataclass(frozen=True)
class ReadinessVerdict:
    staging_score: float
    promote: bool
    certification_passed: bool
    summary: str


class ProductionReadinessExecution:
    """Nightly certification, promotion gates, readiness scoring."""

    PROMOTION_THRESHOLD = 0.75

    def __init__(
        self,
        repository: OperationsRepository,
        certification: ProductionReadinessCertification,
        slos: ProductionSLOs | None = None,
    ) -> None:
        self._repo = repository
        self._cert = certification
        self._slos = slos or ProductionSLOs()

    async def nightly_run(
        self,
        signals: dict[str, Any],
        *,
        chaos_components: dict[str, Any] | None = None,
    ) -> ReadinessVerdict:
        report = await self._cert.run(signals=signals, chaos_components=chaos_components)
        burnin_h = float(signals.get("health_score", 0.8))
        epistemic = float(signals.get("epistemic_stability", 0.8))
        score = self._compute_staging_score(report.passed, burnin_h, epistemic, signals)
        self._repo.save_readiness_score(
            staging_score=score,
            certification_passed=report.passed,
            burnin_health=burnin_h,
            epistemic_stability=epistemic,
            detail={"gates": [g.gate_id for g in report.gates if g.passed], "summary": report.summary},
        )
        return ReadinessVerdict(
            staging_score=score,
            promote=score >= self.PROMOTION_THRESHOLD and report.passed,
            certification_passed=report.passed,
            summary=report.summary,
        )

    @staticmethod
    def _compute_staging_score(
        cert_passed: bool,
        burnin_health: float,
        epistemic: float,
        signals: dict,
    ) -> float:
        if not cert_passed:
            return 0.3
        backlog_penalty = min(0.2, float(signals.get("queue_backlog", 0)) / 2500)
        return round(
            0.4 * burnin_health + 0.35 * epistemic + 0.25 * (1.0 - backlog_penalty),
            4,
        )

    def run_sync_certify(self, signals: dict[str, Any]) -> ReadinessVerdict:
        return asyncio.run(self.nightly_run(signals))
