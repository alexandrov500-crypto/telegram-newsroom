from __future__ import annotations

from pathlib import Path

from bot.live_ops.anomaly_hold import AnomalyHold
from bot.live_ops.audience_safety import AudienceSafety
from bot.live_ops.canary_mode import CanaryPublisher
from bot.live_ops.channel_settings import ControlledLiveSettings
from bot.live_ops.controlled_coordinator import ControlledLiveCoordinator
from bot.live_ops.incident_freeze import IncidentFreeze
from bot.live_ops.live_feedback import LiveFeedbackLoop
from bot.live_ops.metrics_snapshot import LiveMetricsSnapshotter
from bot.live_ops.operator_override import OperatorOverride
from bot.live_ops.publish_guard import LiveChannelPublishGuard
from bot.live_ops.publish_trace import PublishTraceStore
from bot.live_ops.repository import LiveChannelRepository
from bot.live_ops.rollback_control import RollbackControl
from bot.live_ops.source_quarantine import SourceQuarantine
from bot.live_ops.startup_validation import ControlledLiveStartupValidator


def build_controlled_live_stack(db_path: Path) -> ControlledLiveCoordinator:
    settings = ControlledLiveSettings.from_env()
    repo = LiveChannelRepository(db_path)
    canary = CanaryPublisher(settings)
    freeze = IncidentFreeze(settings, repo)
    override = OperatorOverride(repo)
    quarantine = SourceQuarantine(
        db_path,
        bad_threshold=settings.source_quarantine_threshold,
        cooldown_hours=settings.source_quarantine_hours,
    )
    return ControlledLiveCoordinator(
        settings=settings,
        repository=repo,
        publish_guard=LiveChannelPublishGuard(
            settings,
            repo,
            canary,
            freeze,
            override,
            quarantine,
        ),
        canary=canary,
        rollback=RollbackControl(repo, enabled=settings.enable_rollback),
        anomaly=AnomalyHold(settings, repo),
        audience=AudienceSafety(repo),
        feedback=LiveFeedbackLoop(repo),
        freeze=freeze,
        override=override,
        publish_trace=PublishTraceStore(db_path),
        source_quarantine=quarantine,
        metrics=LiveMetricsSnapshotter(
            db_path,
            interval_sec=settings.metrics_snapshot_interval_sec,
        ),
        startup_validator=ControlledLiveStartupValidator(db_path, settings),
    )
