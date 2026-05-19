from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from bot.rc1.activation.workflow import ActivationStage, PublicActivationOrchestrator
from bot.rc1.baselines.engine import BaselineEngine
from bot.rc1.config.registry import NewsroomConfigRegistry
from bot.rc1.config.validation import ConfigValidationGraph, ConfigValidationReport
from bot.rc1.dashboard.launch import LaunchDashboardBuilder
from bot.rc1.hardening.failure_modes import FailureModeGuard
from bot.rc1.lockdown import Rc1LockdownController
from bot.rc1.operator.ux import OperatorUxHub
from bot.rc1.profiling.runtime import RuntimeProfiler
from bot.rc1.repository import Rc1Repository
from bot.rc1.settings import RC1_BUILD_ID, Rc1Settings
from bot.rc1.validation.live_traffic import LiveTrafficValidator

logger = logging.getLogger(__name__)


@dataclass
class Rc1Coordinator:
    settings: Rc1Settings
    repository: Rc1Repository
    config_registry: NewsroomConfigRegistry
    config_validator: ConfigValidationGraph
    lockdown: Rc1LockdownController
    profiler: RuntimeProfiler
    baselines: BaselineEngine
    failure_guard: FailureModeGuard
    activation: PublicActivationOrchestrator
    live_validation: LiveTrafficValidator
    operator_ux: OperatorUxHub
    dashboard: LaunchDashboardBuilder
    _config_report: ConfigValidationReport | None = None
    _signals_fn: Callable[[], dict[str, Any]] | None = None
    _previous_snapshot: dict[str, Any] = field(default_factory=dict)

    def configure_signals(self, fn: Callable[[], dict[str, Any]]) -> None:
        self._signals_fn = fn

    async def startup(self) -> ConfigValidationReport:
        self.config_registry = NewsroomConfigRegistry.collect(build_id=RC1_BUILD_ID)
        self._config_report = self.config_validator.validate(self.config_registry)
        self.repository.save_config_fingerprint(
            fingerprint=self._config_report.fingerprint,
            config=self.config_registry.to_dict(),
            issues=[f"{i.code}: {i.message}" for i in self._config_report.issues],
        )
        if self.settings.lockdown_mode:
            self.lockdown.enable()
        row = self.repository.get_activation()
        if row is None:
            self.repository.set_activation(
                stage=ActivationStage.PRECHECK.value,
                previous=None,
                operator_signoff=None,
                snapshot={"build": RC1_BUILD_ID},
                rollback_point="PRECHECK",
            )
        if not self._config_report.passed:
            logger.error(
                "event=rc1_config_validation_failed issues=%d",
                len(self._config_report.issues),
            )
        else:
            logger.info("event=rc1_startup_ok fingerprint=%s", self._config_report.fingerprint)
        return self._config_report

    async def tick(self, signals: dict[str, Any] | None = None) -> dict[str, Any]:
        sig = signals or (self._signals_fn() if self._signals_fn else {})
        queue = int(sig.get("queue_depth", 0))
        dlq = int(sig.get("event_bus_dlq", 0))

        if self.settings.baselines_enabled:
            self.baselines.ingest(
                queue_depth=queue,
                cognition_sec=sig.get("cognition_sec"),
                budget_hour=float(sig.get("budget_hour", 0)),
                retry_rate=float(sig.get("retry_rate", 0)),
            )

        if self.settings.profiling_enabled:
            if sig.get("cognition_sec"):
                self.profiler.record_cognition("pipeline", float(sig["cognition_sec"]) * 1000)
            self.profiler.record_queue("editorial", queue)
            if sig.get("event_loop_lag_ms"):
                self.profiler.record_event_loop_lag(float(sig["event_loop_lag_ms"]))

        failure_issues = self.failure_guard.scan(
            dlq_count=dlq,
            queue_depth=queue,
            stale_workers=int(sig.get("worker_stale", 0)),
            replay_pending=int(sig.get("event_bus_pending", 0)),
        )
        for issue in failure_issues:
            self.operator_ux.enqueue_alert(
                issue["id"],
                severity=issue["severity"],
                title=issue["id"].replace("_", " ").title(),
                body=f"Detected during RC1 tick",
                remediation=issue.get("remediation", "/system_risk"),
            )

        validation = {}
        if self.settings.live_validation_enabled:
            validation = self.live_validation.evaluate(
                shadow_publish_ratio=float(sig.get("shadow_ratio", 1.0)),
                delivery_success=float(sig.get("telegram_health", 1.0)),
                trust_avg=float(sig.get("trust_score", 0.85)),
                replay_ok=bool(sig.get("replay_ok", True)),
            )
            self.repository.save_validation_scores(
                go_live_confidence=validation["go_live_confidence"],
                publish_integrity=validation["publish_integrity"],
                detail=validation,
            )

        current_snap = {
            "activation": self.activation.current_stage().value,
            "queue": queue,
            "confidence": validation.get("go_live_confidence", 0),
        }
        result = {
            "config_fingerprint": self._config_report.fingerprint if self._config_report else "",
            "activation_stage": self.activation.current_stage().value,
            "failure_issues": failure_issues,
            "validation": validation,
            "baseline_anomaly": self.baselines.anomaly_report(
                {"queue_depth": float(queue)},
            ),
            "lockdown": self.lockdown.snapshot(),
        }
        self._previous_snapshot = current_snap
        return result

    def config_status_text(self) -> str:
        if self._config_report is None:
            return "Config not validated — restart required."
        return "\n".join(self._config_report.summary_lines())

    def config_diff_text(self) -> str:
        stored = self.repository.get_config_fingerprint()
        self.config_registry = NewsroomConfigRegistry.collect(build_id=RC1_BUILD_ID)
        changes = self.config_validator.diff(self.config_registry, stored)
        lines = ["<b>Config diff</b>"]
        if stored:
            lines.append(f"Stored: <code>{stored.get('fingerprint', '?')}</code>")
        lines.append(f"Current: <code>{self.config_registry.fingerprint()}</code>")
        lines.extend(f"• {c}" for c in changes[:12])
        if len(changes) > 12:
            lines.append(f"<i>+{len(changes) - 12} more</i>")
        return "\n".join(lines)

    def launch_dashboard_text(self, sig: dict[str, Any] | None = None) -> str:
        sig = sig or (self._signals_fn() if self._signals_fn else {})
        cert = sig.get("certification", {})
        return self.dashboard.build(
            certification_state=cert.get("state", "NOT_READY"),
            certification_score=float(cert.get("score", 0)),
            rollout_stage=sig.get("rollout_stage", "INTERNAL_SHADOW"),
            risk_score=1.0 - float(sig.get("stability_score", 0.8)),
            slo_violations=int(sig.get("slo_violations", 0)),
            publish_health=float(sig.get("publish_health", 1.0)),
            telegram_health=float(sig.get("telegram_health", 1.0)),
            ai_spend_usd=float(sig.get("ai_spend_usd", 0)),
            trust_score=float(sig.get("trust_score", 0.85)),
            active_incidents=int(sig.get("active_incidents", 0)),
            rollback_ready=True,
            confidence_trend=float(sig.get("go_live_confidence", 0)),
            activation_stage=self.activation.current_stage().value,
            rc_lockdown=self.lockdown.active,
        )

    def save_profile_snapshot(self) -> None:
        profile = self.profiler.bottleneck_report()
        self.repository.save_runtime_profile(profile)
