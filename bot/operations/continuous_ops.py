from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from bot.operations.archaeology import FailureArchaeology
from bot.operations.evidence_bundles import ContinuousEvidenceGenerator
from bot.operations.incident_lifecycle import IncidentLifecycleManager
from bot.operations.longevity_reports import LongevityReportGenerator
from bot.operations.operator_workflow_reports import OperatorWorkflowReportGenerator
from bot.operations.operational_readiness import (
    OperationalReadinessScore,
    compute_operational_readiness,
)
from bot.operations.repository import OperationsRepository
from bot.operations.runtime_supervisor import RuntimeSupervisor
from bot.operations.replay_hardening import ReplaySustainability
from bot.publishing.telegram_reliability import TelegramDeliveryReliability
from bot.staging.publish_safety_monitor import PublishSafetyMonitor

logger = logging.getLogger(__name__)


@dataclass
class ContinuousOpsTickResult:
    supervisor: dict[str, Any]
    readiness: OperationalReadinessScore | None = None
    evidence_bundle_id: str | None = None
    longevity_period: str | None = None
    operator_usability: dict[str, Any] | None = None
    publish_safety_issues: list[str] | None = None


class ContinuousOperationsCoordinator:
    """Wires runtime hardening, Telegram reliability, feed chaos, replay, incidents."""

    def __init__(
        self,
        repository: OperationsRepository,
        archaeology: FailureArchaeology,
        replay: ReplaySustainability,
        *,
        queue_backlog_fn: Callable[[], int] | None = None,
        replay_lag_fn: Callable[[], float] | None = None,
    ) -> None:
        from bot.ingestion.feed_resilience import FeedResilienceLayer

        self.repository = repository
        self.feed_resilience = FeedResilienceLayer(repository)
        self.telegram_delivery = TelegramDeliveryReliability(repository)
        self.incidents = IncidentLifecycleManager(repository, archaeology)
        self.evidence = ContinuousEvidenceGenerator(repository)
        self.longevity = LongevityReportGenerator(repository)
        self.operator_reports = OperatorWorkflowReportGenerator(repository)
        self.replay = replay
        self._supervisor = RuntimeSupervisor(
            queue_backlog_fn=queue_backlog_fn,
            replay_lag_fn=replay_lag_fn,
            stuck_approvals_fn=lambda: repository.count_stuck_approvals(),
        )
        self._publish_safety: PublishSafetyMonitor | None = None

    def attach_publish_safety(self, monitor: PublishSafetyMonitor) -> None:
        self._publish_safety = monitor

    def configure_runtime_callbacks(
        self,
        *,
        queue_backlog_fn: Callable[[], int] | None = None,
        replay_lag_fn: Callable[[], float] | None = None,
    ) -> None:
        if queue_backlog_fn is not None:
            self._supervisor._queue_backlog_fn = queue_backlog_fn
        if replay_lag_fn is not None:
            self._supervisor._replay_lag_fn = replay_lag_fn

    async def runtime_probe(self) -> dict[str, Any]:
        report = await self._supervisor.probe()
        await self._supervisor.attempt_recovery(report)
        return {
            "stalled_loops": report.stalled_loops,
            "stalled_tasks": report.stalled_tasks,
            "replay_lag_sec": report.replay_lag_sec,
            "queue_backlog": report.queue_backlog,
            "stuck_approvals": report.stuck_approvals,
            "recovery_actions": report.recovery_actions,
        }

    async def continuous_tick(
        self,
        *,
        signals: dict[str, Any],
        ops_report: dict[str, Any],
        run_evidence: bool = False,
        run_longevity: str | None = None,
        run_readiness: bool = True,
        run_operator_report: bool = False,
        bot: Any | None = None,
        channel_id: int | None = None,
    ) -> ContinuousOpsTickResult:
        supervisor = await self.runtime_probe()
        ops_report["stalled_loops"] = supervisor.get("stalled_loops", [])

        replay_health = self.replay.measure_replay_health()
        sustainability = max(
            0.0,
            min(
                1.0,
                1.0
                - replay_health.divergence_rate * 2
                - min(0.5, replay_health.storage_rows / 5_000_000),
            ),
        )
        try:
            from bot.observability.metrics import set_replay_sustainability_score

            set_replay_sustainability_score(sustainability)
        except Exception:
            pass
        ops_report["replay_sustainability"] = sustainability

        quarantined = sum(
            1
            for row in self.repository.feed_health_report(limit=100)
            if float(row.get("reliability_score", 1)) < 0.25
        )
        total_feeds = max(len(self.repository.feed_health_report(limit=100)), 1)
        signals["feed_quarantine_rate"] = quarantined / total_feeds
        failures = self.repository.telegram_delivery_failure_count(hours=6)
        total_out = failures + max(1, int(self.repository.telegram_delivery_success_rate(hours=6) * 10))
        signals["telegram_failure_rate_6h"] = failures / max(total_out, 1)

        readiness: OperationalReadinessScore | None = None
        if run_readiness:
            readiness = compute_operational_readiness(signals=signals, ops_report=ops_report)
            try:
                from bot.observability.metrics import set_operational_readiness_score

                set_operational_readiness_score(readiness.overall)
            except Exception:
                pass
            self.repository.save_readiness_score(
                staging_score=readiness.overall,
                certification_passed=readiness.overall >= 0.82,
                burnin_health=float(ops_report.get("long_run_health", 0.8)),
                epistemic_stability=float(signals.get("epistemic_stability", 1.0)),
                detail={
                    "components": readiness.components,
                    "blockers": readiness.blockers,
                    "trend": readiness.trend,
                },
            )

        evidence_id: str | None = None
        if run_evidence:
            bundle = self.evidence.build_bundle(signals=signals, ops_report=ops_report)
            self.evidence.persist(bundle)
            evidence_id = bundle.bundle_id
            logger.info("event=evidence_bundle_persisted bundle_id=%s", evidence_id)

        longevity_period: str | None = None
        if run_longevity:
            report = self.longevity.generate(period=run_longevity, signals=signals)
            self.longevity.write_artifact(report)
            longevity_period = run_longevity

        operator_usability: dict[str, Any] | None = None
        if run_operator_report:
            operator_usability = self.operator_reports.usability_summary(hours=24)

        publish_issues: list[str] | None = None
        if self._publish_safety is not None and bot is not None:
            safety = await self._publish_safety.check_channel_permissions(bot, channel_id)
            publish_issues = list(safety.issues)
            if publish_issues:
                self.incidents.open_incident(
                    title="Publish safety check failed",
                    severity="warning",
                    detail="; ".join(publish_issues),
                    correlation_key="publish_safety",
                    suggested_action="Verify channel permissions and shadow mode",
                )

        return ContinuousOpsTickResult(
            supervisor=supervisor,
            readiness=readiness,
            evidence_bundle_id=evidence_id,
            longevity_period=longevity_period,
            operator_usability=operator_usability,
            publish_safety_issues=publish_issues,
        )

    def feed_quarantine_count(self) -> int:
        with self.repository._connect() as conn:
            try:
                row = conn.execute(
                    "SELECT COUNT(*) AS c FROM ops_feed_quarantine"
                ).fetchone()
                return int(row["c"]) if row else 0
            except Exception:
                return 0
