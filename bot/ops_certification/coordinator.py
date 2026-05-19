from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from bot.ops_certification.certification.engine import (
    CertificationResult,
    CertificationState,
    ProductionCertificationEngine,
)
from bot.ops_certification.chaos.scheduler import ChaosDrillScheduler
from bot.ops_certification.chaos.scenarios import ChaosDrillRunner, ChaosRunResult, ChaosScenario
from bot.ops_certification.governance.controller import GovernanceController
from bot.ops_certification.incidents.workflows import IncidentWorkflowEngine
from bot.ops_certification.longevity.month_uptime import LongevityProtector
from bot.ops_certification.mesh.regional import RegionalMeshFoundation
from bot.ops_certification.reporting.executive import ExecutiveReportGenerator
from bot.ops_certification.repository import OpsCertificationRepository
from bot.ops_certification.security.audit_chain import ImmutableAuditChain, SecurityPostureMonitor
from bot.ops_certification.settings import OpsCertificationSettings
from bot.ops_certification.slo.engine import SloEngine

logger = logging.getLogger(__name__)


@dataclass
class OpsCertificationCoordinator:
    settings: OpsCertificationSettings
    repository: OpsCertificationRepository
    slo: SloEngine
    certification: ProductionCertificationEngine
    chaos: ChaosDrillRunner
    chaos_scheduler: ChaosDrillScheduler
    audit: ImmutableAuditChain
    security: SecurityPostureMonitor
    incidents: IncidentWorkflowEngine
    longevity: LongevityProtector
    governance: GovernanceController
    mesh: RegionalMeshFoundation
    reporting: ExecutiveReportGenerator
    _last_cert: CertificationResult | None = None
    _last_chaos: ChaosRunResult | None = None
    _tick: int = 0
    _signals_fn: Callable[[], dict[str, Any]] | None = None

    def configure_signals(self, fn: Callable[[], dict[str, Any]]) -> None:
        self._signals_fn = fn

    async def startup(self) -> None:
        self.governance.load()
        logger.info("event=ops_certification_installed")

    async def tick(self, signals: dict[str, Any] | None = None) -> dict[str, Any]:
        self._tick += 1
        sig = signals or (self._signals_fn() if self._signals_fn else {})

        if self.settings.slo_enabled:
            self.slo.ingest_operational_signals(
                publish_latency_sec=sig.get("publish_latency_sec"),
                cognition_sec=sig.get("cognition_sec"),
                delivery_ok=sig.get("delivery_ok"),
                queue_depth=int(sig.get("queue_depth", 0)),
                uptime_ok=bool(sig.get("uptime_ok", True)),
            )
            for ev in self.slo.evaluate_all():
                self.slo._export_gauges(ev)
                self.repository.record_slo_snapshot(
                    slo_name=ev.name.value,
                    window_hours=ev.window_hours,
                    compliance_ratio=ev.compliance_ratio,
                    burn_rate=ev.burn_rate,
                    error_budget_remaining=ev.error_budget_remaining,
                    violated=ev.violated,
                )

        memory_mb = float(sig.get("memory_mb", 0))
        queue_depth = int(sig.get("queue_depth", 0))
        if self.settings.longevity_enabled:
            self.longevity.tick(memory_mb=memory_mb, queue_depth=queue_depth)

        if self.settings.mesh_aggregation_enabled:
            self.mesh.heartbeat_local(healthy=bool(sig.get("uptime_ok", True)))

        cert = self._evaluate_certification(sig)
        self._last_cert = cert
        try:
            from bot.observability.metrics import set_certification_metrics, set_governance_frozen

            set_certification_metrics(cert.score, cert.state.value)
            set_governance_frozen(self.governance.snapshot().get("editorial_frozen", False))
        except Exception:
            pass
        self.repository.set_certification_state(
            state=cert.state.value,
            score=cert.score,
            blockers=list(cert.blockers),
            certified=cert.state == CertificationState.CERTIFIED,
        )

        if (
            self.settings.chaos_scheduled
            and self.settings.chaos_enabled
            and self._tick % 1440 == 0
        ):
            rollback_cb = sig.get("on_chaos_rollback")
            self._last_chaos = await self.chaos_scheduler.maybe_run_scheduled(
                tick=self._tick,
                on_rollback=rollback_cb,
                safety_check=lambda: cert.score,
            )
            if self._last_chaos is not None:
                self.repository.record_chaos_run(
                    run_id=self._last_chaos.run_id,
                    scenario=self._last_chaos.scenario.value,
                    status=self._last_chaos.status,
                    survivability_score=self._last_chaos.survivability_score,
                    detail=self._last_chaos.detail,
                    ended=True,
                )

        return {
            "certification": cert.to_dict(),
            "slo_violations": sum(1 for e in self.slo.evaluate_all() if e.violated),
            "longevity": {
                "aging_score": self.longevity.runtime_aging_score(),
                "forecast": self.longevity.degradation_forecast(),
            },
            "governance": self.governance.snapshot(),
            "mesh": self.mesh.aggregate_health(),
        }

    def _evaluate_certification(self, sig: dict[str, Any]) -> CertificationResult:
        slo_violations = sum(1 for e in self.slo.evaluate_all() if e.violated)
        return self.certification.evaluate(
            fatal_incidents=int(sig.get("fatal_incidents", 0)),
            worker_stale=int(sig.get("worker_stale", 0)),
            worker_total=int(sig.get("worker_total", 0)),
            replay_ok=bool(sig.get("replay_ok", True)),
            queue_depth=int(sig.get("queue_depth", 0)),
            recovery_ok=bool(sig.get("recovery_ok", True)),
            budget_anomaly=bool(sig.get("budget_anomaly", False)),
            telegram_health=float(sig.get("telegram_health", 1.0)),
            event_bus_dlq=int(sig.get("event_bus_dlq", 0)),
            event_bus_pending=int(sig.get("event_bus_pending", 0)),
            db_ok=bool(sig.get("db_ok", True)),
            memory_trend_ok=self.longevity.fragmentation_risk() < 0.5,
            unbounded_retries=bool(sig.get("unbounded_retries", False)),
            poison_growth=int(sig.get("poison_growth", 0)),
            stability_score=float(sig.get("stability_score", 1.0)),
            slo_violations=slo_violations,
            locked_down=bool(sig.get("locked_down", False)),
        )

    async def run_chaos(
        self,
        scenario: ChaosScenario,
        *,
        on_rollback: Any = None,
    ) -> ChaosRunResult:
        if not self.settings.chaos_enabled:
            result = ChaosRunResult(
                run_id="disabled",
                scenario=scenario,
                status="disabled",
                survivability_score=0.0,
                detail={"reason": "chaos_disabled"},
            )
            return result

        async def _rollback(reason: str) -> None:
            if on_rollback is not None:
                await on_rollback(reason)

        cert = self._last_cert or self._evaluate_certification(
            self._signals_fn() if self._signals_fn else {},
        )
        result = await self.chaos.run(
            scenario,
            on_rollback=_rollback if on_rollback else None,
            safety_check=lambda: cert.score,
        )
        self._last_chaos = result
        self.repository.record_chaos_run(
            run_id=result.run_id,
            scenario=result.scenario.value,
            status=result.status,
            survivability_score=result.survivability_score,
            detail=result.detail,
            ended=True,
        )
        try:
            from bot.observability.metrics import set_chaos_survivability

            set_chaos_survivability(result.survivability_score)
        except Exception:
            pass
        return result

    def certify(self) -> CertificationResult:
        sig = self._signals_fn() if self._signals_fn else {}
        result = self._evaluate_certification(sig)
        self._last_cert = self.certification.certify_if_ready(result)
        self.repository.set_certification_state(
            state=result.state.value,
            score=result.score,
            blockers=list(result.blockers),
            certified=result.state == CertificationState.CERTIFIED,
        )
        return result

    @property
    def last_certification(self) -> CertificationResult | None:
        return self._last_cert

    @property
    def last_chaos(self) -> ChaosRunResult | None:
        return self._last_chaos
