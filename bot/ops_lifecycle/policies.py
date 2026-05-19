from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ArtifactPolicy:
    """Retention policy for one artifact class."""

    name: str
    action: str  # rotate | compact | summarize | retain | archive | expire
    retention_days: int
    table: str | None = None
    time_column: str = "created_at"
    path_glob: str | None = None
    severity_column: str | None = None
    keep_critical_days: int | None = None


def _days(env_key: str, default: int) -> int:
    try:
        return int(os.getenv(env_key, str(default)))
    except ValueError:
        return default


def default_policies() -> list[ArtifactPolicy]:
    return [
        ArtifactPolicy("runtime_pulses", "compact", _days("OPS_RETAIN_PULSES_DAYS", 30), path_glob="pulses/*.jsonl"),
        ArtifactPolicy("live_metrics_snapshots", "compact", _days("OPS_RETAIN_METRICS_DAYS", 90), table="live_metrics_snapshots"),
        ArtifactPolicy("ops_attention_log", "summarize", _days("OPS_RETAIN_ATTENTION_DAYS", 14), table="ops_attention_log"),
        ArtifactPolicy("live_publish_trace", "retain", _days("OPS_RETAIN_PUBLISH_TRACE_DAYS", 180), table="live_publish_trace", time_column="updated_at"),
        ArtifactPolicy("live_incident_timeline", "summarize", _days("OPS_RETAIN_TIMELINE_INFO_DAYS", 30), table="live_incident_timeline", severity_column="severity", keep_critical_days=_days("OPS_RETAIN_TIMELINE_CRITICAL_DAYS", 365)),
        ArtifactPolicy("live_channel_incidents", "rotate", _days("OPS_RETAIN_INCIDENTS_DAYS", 90), table="live_channel_incidents"),
        ArtifactPolicy("runtime_state_snapshot", "compact", _days("OPS_RETAIN_RUNTIME_SNAPSHOT_DAYS", 30), table="runtime_state_snapshot", time_column="timestamp"),
        ArtifactPolicy("editorial_quality_scores", "compact", _days("OPS_RETAIN_EDITORIAL_QUALITY_DAYS", 90), table="editorial_quality_scores"),
        ArtifactPolicy("editorial_priority_scores", "compact", _days("OPS_RETAIN_EDITORIAL_PRIORITY_DAYS", 90), table="editorial_priority_scores"),
        ArtifactPolicy("editorial_story_events", "archive", _days("OPS_RETAIN_STORY_EVENTS_DAYS", 120), table="editorial_story_events"),
        ArtifactPolicy(
            "ops_incident_bundles",
            "archive",
            _days("OPS_RETAIN_BUNDLE_DAYS", 180),
            table="ops_incident_bundles",
        ),
        ArtifactPolicy("ops_forensics_traces", "expire", _days("OPS_RETAIN_FORENSICS_TRACE_DAYS", 45), table="ops_forensics_traces"),
    ]
