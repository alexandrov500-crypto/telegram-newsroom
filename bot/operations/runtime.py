from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bot.operations.archaeology import FailureArchaeology
from bot.operations.burnin import BurnInRunner
from bot.operations.burnin_reports import BurnInReportGenerator
from bot.operations.certification import ProductionReadinessCertification
from bot.operations.economics import ProductionEconomics
from bot.operations.economics_reports import ProductionEconomicsReports
from bot.operations.editorial_review import EditorialValidationWorkflow
from bot.operations.epistemic_monitor import EpistemicStabilityMonitor
from bot.operations.ergonomics import OperationalErgonomics
from bot.operations.feed_validation import FeedValidationLayer
from bot.operations.incident_ops import IncidentArchaeologyOps
from bot.operations.observability_export import ObservabilityPlatform
from bot.operations.operator_workflows import OperatorWorkflowValidation
from bot.operations.operator_workflow_reports import OperatorWorkflowReportGenerator
from bot.operations.evidence_bundles import ContinuousEvidenceGenerator
from bot.operations.incident_lifecycle import IncidentLifecycleManager
from bot.operations.longevity_reports import LongevityReportGenerator
from bot.operations.operational_readiness import compute_operational_readiness
from bot.operations.readiness_execution import ProductionReadinessExecution
from bot.operations.replay_hardening import ReplaySustainability
from bot.operations.runtime_supervisor import RuntimeSupervisor
from bot.operations.repository import OperationsRepository
from bot.operations.simplification import OperationalSimplification
from bot.operations.storage import StorageSustainability
from bot.operations.types import ProductionSLOs
from bot.staging.long_run import LongRunHealthTracker

logger = logging.getLogger(__name__)


@dataclass
class OperationsPlatform:
    """Production operationalization facade."""

    repository: OperationsRepository
    feed_validation: FeedValidationLayer
    burnin: BurnInRunner
    burnin_reports: BurnInReportGenerator
    storage: StorageSustainability
    replay: ReplaySustainability
    economics: ProductionEconomics
    economics_reports: ProductionEconomicsReports
    editorial_review: EditorialValidationWorkflow
    archaeology: FailureArchaeology
    incident_ops: IncidentArchaeologyOps
    ergonomics: OperationalErgonomics
    operator_workflows: OperatorWorkflowValidation
    epistemic_monitor: EpistemicStabilityMonitor
    simplification: OperationalSimplification
    certification: ProductionReadinessCertification
    readiness: ProductionReadinessExecution
    observability: ObservabilityPlatform
    long_run: LongRunHealthTracker
    evidence: ContinuousEvidenceGenerator
    incidents: IncidentLifecycleManager
    longevity: LongevityReportGenerator
    feed_resilience: object
    runtime_supervisor: RuntimeSupervisor
    operator_reports: OperatorWorkflowReportGenerator
    slos: ProductionSLOs
    node_id: str
    region: str
    db_path: Path

    async def operational_tick(
        self,
        *,
        signals: dict[str, Any],
        run_feed_validation: bool = False,
        run_storage_maintenance: bool = False,
        run_burnin_report: bool = False,
        run_epistemic_snapshot: bool = False,
        run_replay_indexes: bool = False,
        run_daily_economics: bool = False,
        run_nightly_cert: bool = False,
        run_evidence_bundle: bool = False,
        run_longevity_report: str | None = None,
        run_operator_workflow_report: bool = False,
        epistemic_detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        report: dict[str, Any] = {}

        if run_feed_validation:
            from bot.observability.loop_diagnostics import timed_async_job

            async with timed_async_job("feed_validation_catalog"):
                results = await self.feed_validation.validate_catalog_async()
            report["feeds_validated"] = len(results)
            report["feeds_unreliable"] = sum(1 for r in results if r.reliability < 0.4)

        health = float(signals.get("health_score", 1.0))
        self.burnin.record_sample(
            {
                "health_score": health,
                "queue_backlog": signals.get("queue_backlog", 0),
                "epistemic_stability": signals.get("epistemic_stability", 1.0),
                "mesh_health": signals.get("mesh_health", 1.0),
                "memory_mb": signals.get("memory_mb", 0),
                "gossip_budget": signals.get("gossip_budget", 0),
            }
        )

        if run_storage_maintenance:
            import asyncio

            from bot.observability.loop_diagnostics import timed_async_job

            async with timed_async_job("storage_maintenance"):
                compacted = await asyncio.to_thread(self.storage.run_maintenance)
            report["storage_compacted"] = len(compacted)
            signals["storage_growth_mb_day"] = self.storage.estimate_growth_mb_per_day()

        if run_replay_indexes:
            report["replay_indexes"] = self.replay.ensure_replay_indexes()
            replay_health = self.replay.measure_replay_health()
            report["replay_divergence"] = replay_health.divergence_rate
            signals["replay_divergence"] = replay_health.divergence_rate

        cost = self.economics.record(
            region=self.region,
            token_spend=float(signals.get("token_spend_usd", 0)),
            replay_cost=float(signals.get("replay_cost_usd", 0)),
            cognition_cost=float(signals.get("cognition_cost_usd", 0)),
            federation_cost=float(signals.get("federation_cost_usd", 0)),
        )
        report["cost_mode"] = self.economics.recommend_mode(cost.total_usd)
        report["cost_total_usd"] = cost.total_usd

        if run_daily_economics:
            daily = self.economics_reports.generate_daily_report(
                token=float(signals.get("token_spend_usd", 0)),
                replay=float(signals.get("replay_cost_usd", 0)),
                cognition=float(signals.get("cognition_cost_usd", 0)),
                federation=float(signals.get("federation_cost_usd", 0)),
                publishes=int(signals.get("publishes_today", 0)),
            )
            report["daily_cost_usd"] = daily.total_usd
            report["cost_anomaly"] = daily.anomaly

        if cost.anomaly:
            self.simplification.dedupe_enqueue(
                alert_key=f"cost:{self.region}",
                category="cost",
                title="Daily cost budget pressure",
                detail={"total_usd": cost.total_usd, "explanation": cost.explanation},
            )

        if signals.get("epistemic_stability", 1.0) < self.slos.epistemic_stability_min:
            self.simplification.dedupe_enqueue(
                alert_key="epistemic:stability",
                category="epistemic",
                title="Epistemic stability below SLO",
                detail={"stability": signals.get("epistemic_stability")},
            )

        if run_epistemic_snapshot:
            detail = epistemic_detail or {}
            ep_report = self.epistemic_monitor.record_snapshot(
                confidence_mean=float(detail.get("confidence_mean", 0.7)),
                uncertainty_mean=float(detail.get("uncertainty_mean", 0.3)),
                open_contradictions=int(detail.get("open_contradictions", 0)),
                misinfo_pressure=float(detail.get("misinfo_pressure", 0.0)),
                diversity_score=float(detail.get("diversity_score", 0.5)),
            )
            report["epistemic_alerts"] = list(ep_report.alerts)
            for alert in ep_report.alerts:
                self.simplification.dedupe_enqueue(
                    alert_key=f"epistemic:{alert}",
                    category="epistemic",
                    title=f"Epistemic drift: {alert}",
                    detail={"diversity": ep_report.diversity_score},
                )

        active = self.repository.active_burnin()
        if run_burnin_report and active:
            period = active.get("profile", "rolling")
            if period in ("24h", "7d", "30d"):
                summary = self.burnin_reports.generate_operational_report(
                    active["run_id"],
                    period=period,
                )
                try:
                    self.burnin_reports.write_full_report(summary)
                    self.burnin_reports.write_report_file(
                        summary,
                        Path("docs") / "BURN_IN_REPORT_AUTO.md",
                    )
                except OSError:
                    logger.debug("event=burnin_report_write_skipped")
            else:
                summary = self.burnin_reports.generate_period_report(
                    active["run_id"],
                    period=period,
                )
            report["burnin_regressions"] = list(summary.regressions)

        if run_nightly_cert:
            verdict = await self.readiness.nightly_run(signals)
            report["staging_score"] = verdict.staging_score
            report["promote_ready"] = verdict.promote

        triage = self.ergonomics.triage_open()
        report["operator_alerts_open"] = len(triage)
        report["operator_fatigue"] = self.ergonomics.fatigue_estimate(
            signals.get("alerts_last_hour", len(triage))
        )
        dashboard = self.simplification.consolidate_dashboard()
        report["escalation_categories"] = dashboard.top_categories

        export = self.observability.build_export(
            mesh_report=signals.get("mesh_report"),
            epistemic_snap=signals.get("epistemic_snap"),
            contradictions=signals.get("contradictions"),
            operator_alerts=[{"title": t.title, "category": t.category} for t in triage],
        )
        report["observability_export_bytes"] = len(export.to_json())

        supervisor_report = await self.runtime_supervisor.probe()
        report["stalled_loops"] = supervisor_report.stalled_loops
        report["runtime_recovery_actions"] = supervisor_report.recovery_actions
        if supervisor_report.recovery_actions:
            await self.runtime_supervisor.attempt_recovery(supervisor_report)

        replay_sustain = self.replay.assess_sustainability()
        report["replay_sustainability"] = replay_sustain
        if replay_sustain.get("storage_acceleration"):
            self.simplification.dedupe_enqueue(
                alert_key="replay:storage_pressure",
                category="replay",
                title="Replay storage acceleration detected",
                detail=replay_sustain,
            )

        replay_health = self.replay.measure_replay_health()
        lr = self.long_run.score(
            memory_mb=float(signals.get("memory_mb", 0)),
            storage_rows=replay_health.storage_rows,
            replay_divergence=replay_health.divergence_rate,
            open_contradictions=int((epistemic_detail or {}).get("open_contradictions", 0)),
            confidence_mean=float((epistemic_detail or {}).get("confidence_mean", 0.7)),
            mesh_health=float(signals.get("mesh_health", 1.0)),
        )
        report["long_run_health"] = lr.score
        try:
            from bot.observability.metrics import (
                set_event_amplification,
                set_long_run_health,
                set_replay_lag,
                set_scheduler_pressure,
            )

            set_replay_lag(replay_health.reconstruction_latency_ms / 1000.0)
            set_long_run_health(lr.score)
            backlog = float(signals.get("queue_backlog", 0))
            set_scheduler_pressure(min(1.0, backlog / 1000.0))
            counts = self.repository.table_row_counts()
            sourced = counts.get("sourced_event_log", 1)
            mesh = counts.get("mesh_cognitive_events", 0)
            set_event_amplification(mesh / max(sourced, 1))
        except Exception:
            pass

        if run_evidence_bundle:
            bundle = self.evidence.build_bundle(signals=signals, ops_report=report)
            paths = self.evidence.persist(bundle)
            report["evidence_bundle"] = bundle.bundle_id
            report["evidence_paths"] = [str(p) for p in paths if p]

        if run_longevity_report:
            longevity = self.longevity.generate(run_longevity_report, signals=signals)
            artifact = self.longevity.write_artifact(longevity)
            report["longevity_report"] = run_longevity_report
            report["longevity_artifact"] = str(artifact)

        if run_operator_workflow_report:
            wf = self.operator_reports.build(hours=24)
            report["operator_workflow"] = self.operator_reports.usability_summary(hours=24)
            report["operator_friction"] = wf.friction_notes

        readiness = compute_operational_readiness(signals=signals, ops_report=report)
        report["operational_readiness"] = readiness.overall
        report["readiness_blockers"] = readiness.blockers
        try:
            from bot.observability.metrics import set_operational_readiness_score

            set_operational_readiness_score(readiness.overall)
        except Exception:
            pass
        self.repository.save_readiness_score(
            staging_score=readiness.overall,
            certification_passed=int(readiness.overall >= 0.75),
            burnin_health=float(report.get("long_run_health", 0.8)),
            epistemic_stability=float(signals.get("epistemic_stability", 1.0)),
            detail={"components": readiness.components, "blockers": readiness.blockers},
        )

        return report


def build_operations_platform(
    db_path: Path,
    *,
    node_id: str,
    region: str,
) -> OperationsPlatform:
    repo = OperationsRepository(db_path)
    slos = ProductionSLOs()
    burnin = BurnInRunner(repo)
    ergonomics = OperationalErgonomics(repo)
    certification = ProductionReadinessCertification(repo, slos)
    from bot.ingestion.feed_resilience import FeedResilienceLayer

    archaeology = FailureArchaeology(repo)
    replay = ReplaySustainability(db_path, repo)
    supervisor = RuntimeSupervisor(
        queue_backlog_fn=lambda: 0,
        replay_lag_fn=lambda: 0.0,
        stuck_approvals_fn=lambda: repo.count_stuck_approvals(),
    )
    return OperationsPlatform(
        repository=repo,
        feed_validation=FeedValidationLayer(repo),
        burnin=burnin,
        burnin_reports=BurnInReportGenerator(repo, burnin),
        storage=StorageSustainability(db_path, repo),
        replay=replay,
        economics=ProductionEconomics(repo, slos),
        economics_reports=ProductionEconomicsReports(repo, slos),
        editorial_review=EditorialValidationWorkflow(repo),
        archaeology=archaeology,
        incident_ops=IncidentArchaeologyOps(archaeology, repo),
        ergonomics=ergonomics,
        operator_workflows=OperatorWorkflowValidation(repo, ergonomics),
        epistemic_monitor=EpistemicStabilityMonitor(repo),
        simplification=OperationalSimplification(repo, ergonomics),
        certification=certification,
        readiness=ProductionReadinessExecution(repo, certification, slos),
        observability=ObservabilityPlatform(),
        long_run=LongRunHealthTracker(repo),
        evidence=ContinuousEvidenceGenerator(repo),
        incidents=IncidentLifecycleManager(repo, archaeology),
        longevity=LongevityReportGenerator(repo),
        feed_resilience=FeedResilienceLayer(repo),
        runtime_supervisor=supervisor,
        operator_reports=OperatorWorkflowReportGenerator(repo),
        slos=slos,
        node_id=node_id,
        region=region,
        db_path=db_path,
    )
