from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from bot.live_ops.anomaly_hold import AnomalyHold
from bot.live_ops.audience_safety import AudienceSafety
from bot.live_ops.canary_mode import CanaryPublisher
from bot.live_ops.channel_settings import ControlledLiveSettings, LiveMode
from bot.live_ops.incident_freeze import IncidentFreeze
from bot.live_ops.live_feedback import LiveFeedbackLoop
from bot.live_ops.metrics_snapshot import LiveMetricsSnapshotter
from bot.live_ops.operator_override import OperatorOverride
from bot.live_ops.ops_alerts import notify_ops_channel
from bot.live_ops.publish_guard import LiveChannelPublishGuard
from bot.live_ops.publish_trace import PublishTraceStore
from bot.live_ops.repository import LiveChannelRepository
from bot.live_ops.rollback_control import RollbackControl
from bot.live_ops.source_quarantine import SourceQuarantine
from bot.live_ops.startup_validation import ControlledLiveStartupValidator
from bot.runtime.state import runtime_state

logger = logging.getLogger(__name__)


class ControlledLiveCoordinator:
    """Controlled real-world Telegram channel operations."""

    def __init__(
        self,
        *,
        settings: ControlledLiveSettings,
        repository: LiveChannelRepository,
        publish_guard: LiveChannelPublishGuard,
        canary: CanaryPublisher,
        rollback: RollbackControl,
        anomaly: AnomalyHold,
        audience: AudienceSafety,
        feedback: LiveFeedbackLoop,
        freeze: IncidentFreeze,
        override: OperatorOverride,
        publish_trace: PublishTraceStore,
        source_quarantine: SourceQuarantine,
        metrics: LiveMetricsSnapshotter,
        startup_validator: ControlledLiveStartupValidator,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.publish_guard = publish_guard
        self.canary = canary
        self.rollback = rollback
        self.anomaly = anomaly
        self.audience = audience
        self.feedback = feedback
        self.freeze = freeze
        self.override = override
        self.publish_trace = publish_trace
        self.source_quarantine = source_quarantine
        self.metrics = metrics
        self.startup_validator = startup_validator
        self._signals_fn: Callable[[], dict[str, Any]] | None = None
        self._tick = 0
        self._startup_report: Any = None
        self._held_last_hour = 0
        self._published_last_hour = 0

    def configure_signals(self, fn: Callable[[], dict[str, Any]]) -> None:
        self._signals_fn = fn

    async def startup(self) -> dict[str, Any]:
        self.repository.ensure_state(live_mode=self.settings.live_mode.value)
        self._startup_report = await self.startup_validator.validate()
        if self._startup_report.forced_shadow:
            self.repository.update_state(live_mode=LiveMode.SHADOW.value)
            runtime_state.shadow_publish_only = True
            await notify_ops_channel(
                self.startup_validator.summary_html(self._startup_report),
                force=True,
            )
        else:
            self.repository.update_state(
                live_mode=self.settings.live_mode.value,
                paused=0,
                frozen=0,
            )
            runtime_state.shadow_publish_only = False
        logger.info(
            "event=controlled_live_installed mode=%s passed=%s",
            self.settings.live_mode.value,
            self._startup_report.passed,
        )
        return {
            "passed": self._startup_report.passed,
            "forced_shadow": self._startup_report.forced_shadow,
        }

    def record_publish_decision(
        self,
        *,
        pending_news_id: int,
        source: str,
        cluster_id: int | None,
        confidence_score: float,
        trust_score: float,
        safety_score: float,
        guard_result: str,
        hold_reason: str | None,
        operator_override: bool,
        published: bool,
        channel_id: int | None = None,
        blockers: list[str] | None = None,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        state = self.repository.get_state() or {}
        return self.publish_trace.record_decision(
            pending_news_id=pending_news_id,
            mode=str(state.get("live_mode", self.settings.live_mode.value)),
            channel=channel_id,
            source=source,
            cluster_id=cluster_id,
            confidence_score=confidence_score,
            trust_score=trust_score,
            safety_score=safety_score,
            guard_result=guard_result,
            hold_reason=hold_reason,
            operator_override=operator_override,
            published=published,
            blockers=blockers,
            correlation_id=correlation_id,
        )

    async def tick(self, *, signals: dict[str, Any] | None = None) -> dict[str, Any]:
        self._tick += 1
        sig = dict(signals or (self._signals_fn() if self._signals_fn else {}))
        fatigue = float(sig.get("publish_fatigue", sig.get("audience_fatigue", 0.2)))
        engagement = float(sig.get("engagement_quality", 0.75))
        self.audience.observe_engagement(
            engagement=engagement,
            silence_rate=fatigue,
        )
        hold = self.anomaly.apply_hold_if_needed()
        if hold:
            await notify_ops_channel(
                "<b>Anomaly hold</b> — publishing frozen after failure spike",
                force=True,
            )
        self.feedback.update_derived_scores()
        state = self.repository.get_state() or {}
        scores = self.feedback.scores()
        snap_metrics = {
            "published_last_hour": self._published_last_hour,
            "held_last_hour": self._held_last_hour,
            "rollback_count": self.rollback.recent_rollback_count(),
            "freeze_count": 1 if state.get("frozen") else 0,
            "engagement_score": engagement,
            "fatigue_score": fatigue,
            "incident_rate": len(self.repository.recent_incidents(limit=5)) / 5.0,
            "channel_health": scores["trust_score"] * scores["content_stability_score"],
        }
        saved = self.metrics.maybe_snapshot(snap_metrics)
        return {
            "live_mode": state.get("live_mode"),
            "paused": bool(state.get("paused")),
            "frozen": bool(state.get("frozen")),
            "trust_score": state.get("trust_score"),
            "content_stability_score": state.get("content_stability_score"),
            "anomaly_hold": hold,
            "publishes_this_hour": state.get("publishes_this_hour", 0),
            "metrics_snapshot": saved is not None,
            "startup_passed": (
                self._startup_report.passed if self._startup_report else True
            ),
        }

    def on_publish_success(self, *, pending_news_id: int) -> None:
        self.feedback.record_publish_success(pending_news_id=pending_news_id)
        self.freeze.record_success()
        self.anomaly.observe_failure(failed=False)
        self._published_last_hour += 1
        self._increment_hourly_count()
        self.publish_trace.update_published(
            pending_news_id,
            published=True,
            guard_result="pass",
        )
        try:
            from bot.ops_forensics.hooks import record_audit, record_timeline

            record_timeline(
                "publish_succeeded",
                severity="info",
                details={"pending_news_id": pending_news_id},
                publish_id=pending_news_id,
            )
            record_audit(
                "publish_succeeded",
                publish_id=pending_news_id,
                payload={"pending_news_id": pending_news_id, "guard_result": "pass"},
            )
        except Exception:
            pass

    def on_publish_failure(self, *, pending_news_id: int, reason: str) -> None:
        self.feedback.record_publish_failure(pending_news_id=pending_news_id, reason=reason)
        self.freeze.record_failure()
        self.anomaly.observe_failure(failed=True)
        self._held_last_hour += 1
        self.publish_trace.update_published(
            pending_news_id,
            published=False,
            guard_result=reason,
        )
        try:
            from bot.ops_forensics.hooks import record_audit, record_timeline

            record_timeline(
                "publish_failed",
                severity="warning",
                details={"pending_news_id": pending_news_id, "reason": reason},
                publish_id=pending_news_id,
            )
            record_audit(
                "publish_failed",
                publish_id=pending_news_id,
                payload={"reason": reason},
            )
        except Exception:
            pass

    def on_mark_bad(self, *, source: str, pending_news_id: int) -> dict[str, Any] | None:
        result = self.source_quarantine.record_bad_post(source)
        try:
            from bot.ops_forensics.hooks import record_timeline

            record_timeline(
                "source_quarantine",
                severity="warning",
                details={"source": source, "quarantine": result},
                publish_id=pending_news_id,
            )
        except Exception:
            pass
        return result

    def _increment_hourly_count(self) -> None:
        bucket = datetime.now(timezone.utc).strftime("%Y%m%d%H")
        state = self.repository.get_state() or {}
        count = int(state.get("publishes_this_hour", 0))
        if state.get("hour_bucket") != bucket:
            count = 0
            self._published_last_hour = 0
            self._held_last_hour = 0
        self.repository.update_state(
            hour_bucket=bucket,
            publishes_this_hour=count + 1,
        )

    def snapshot(self) -> dict[str, Any]:
        state = self.repository.get_state() or {}
        scores = self.feedback.scores()
        runtime_perf: dict[str, Any] = {}
        try:
            from bot.observability.loop_diagnostics import snapshot as loop_perf_snapshot
            from bot.observability.loop_health import snapshot as loop_health_snapshot

            runtime_perf = loop_perf_snapshot()
            runtime_perf["loop_health"] = loop_health_snapshot()
        except Exception:
            pass
        return {
            "enabled": self.settings.enabled,
            "live_mode": state.get("live_mode"),
            "paused": bool(state.get("paused")),
            "frozen": bool(state.get("frozen")),
            "scores": scores,
            "rollback_24h": self.rollback.recent_rollback_count(),
            "success_rate": self.repository.publish_success_rate(),
            "latest_metrics": self.metrics.latest(),
            "quarantined_sources": len(self.source_quarantine.list_active()),
            "runtime_performance": runtime_perf,
        }

    def live_status_html(self) -> str:
        snap = self.snapshot()
        startup = "ok"
        if self._startup_report and not self._startup_report.passed:
            startup = "degraded (shadow)"
        return (
            "<b>Live status</b>\n"
            f"Mode: <code>{snap['live_mode']}</code> · startup: {startup}\n"
            f"Paused: {snap['paused']} · Frozen: {snap['frozen']}\n"
            f"Trust: {snap['scores']['trust_score']:.0%} · "
            f"Stability: {snap['scores']['content_stability_score']:.0%}\n"
            f"Publish success: {snap['success_rate']:.0%}\n"
            f"Quarantined sources: {snap['quarantined_sources']}"
        )

    def channel_health_html(self, signals: dict[str, Any] | None = None) -> str:
        sig = signals or (self._signals_fn() if self._signals_fn else {})
        m = self.metrics.latest() or {}
        perf = self.snapshot().get("runtime_performance") or {}
        lh = perf.get("loop_health") or {}
        lines = [
            "<b>Channel health</b>",
            self.live_status_html().replace("<b>Live status</b>\n", ""),
            f"Queue: {sig.get('queue_depth', '?')}",
            f"Stabilization risk: {float(sig.get('stabilization_risk', 0)):.0%}",
            f"Survivability: {float(sig.get('survivability_score', 0)):.0%}",
            f"Event loop lag avg/max: {perf.get('event_loop_lag_avg', 0):.3f}s / "
            f"{perf.get('event_loop_lag_max', 0):.3f}s",
            f"RSS avg/max: {lh.get('rss_loop_duration_avg', 0):.2f}s / "
            f"{lh.get('rss_loop_duration_max', 0):.2f}s",
            f"Autonomous: {lh.get('autonomous_loop_duration_avg', 0):.2f}s max "
            f"({'passive' if lh.get('autonomous_passive') else 'active'})",
            f"Recovery rate: {lh.get('recovery_rate', 0):.0%}",
        ]
        if m:
            lines.append(f"Health score: {float(m.get('channel_health', 0)):.0%}")
        if perf.get("current_job"):
            lines.append(f"Active job: {perf['current_job']}")
        return "\n".join(lines)

    def dashboard_html(self, signals: dict[str, Any] | None = None) -> str:
        try:
            from bot.operator_ux.service import enhanced_dashboard_html

            return enhanced_dashboard_html(self, signals, db_path=self.repository._db_path)
        except Exception:
            logger.debug("event=enhanced_dashboard_fallback")
        sig = signals or (self._signals_fn() if self._signals_fn else {})
        snap = self.snapshot()
        return self.live_status_html() + f"\nSurvivability: {float(sig.get('survivability_score', 0)):.0%}"

    def trace_html(self, pending_news_id: int) -> str:
        trace = self.publish_trace.get(pending_news_id)
        if not trace:
            return f"No trace for #{pending_news_id}"
        return (
            f"<b>Publish trace</b> #{pending_news_id}\n"
            f"Mode: {trace.get('mode')} · guard: {trace.get('guard_result')}\n"
            f"Published: {trace.get('published')} · hold: {trace.get('hold_reason')}\n"
            f"Trust: {trace.get('trust_score')} · safety: {trace.get('safety_score')}"
        )
