from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class EventType(str, Enum):
    STORY_UPDATED = "StoryUpdated"
    SIGNAL_DETECTED = "SignalDetected"
    TREND_ESCALATED = "TrendEscalated"
    ANOMALY_DETECTED = "AnomalyDetected"
    PUBLISH_FAILED = "PublishFailed"
    IMPACT_FORECAST_GENERATED = "ImpactForecastGenerated"
    PRIORITY_DECIDED = "PriorityDecided"
    POLICY_CHANGED = "PolicyChanged"
    NODE_HEALTH_CHANGED = "NodeHealthChanged"
    REPLAY_STARTED = "ReplayStarted"


@dataclass(frozen=True, slots=True)
class NewsroomEvent:
    event_type: str
    payload: dict[str, Any]
    event_id: str = field(default_factory=lambda: uuid4().hex)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "created_at": self.created_at,
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> NewsroomEvent:
        return cls(
            event_id=str(data.get("event_id", uuid4().hex)),
            event_type=str(data["event_type"]),
            created_at=str(data.get("created_at", datetime.now(timezone.utc).isoformat())),
            payload=dict(data.get("payload") or {}),
        )


def story_updated(*, story_id: int, cluster_id: int | None, importance: float) -> NewsroomEvent:
    return NewsroomEvent(
        event_type=EventType.STORY_UPDATED.value,
        payload={
            "story_id": story_id,
            "cluster_id": cluster_id,
            "importance": importance,
        },
    )


def signal_detected(*, signal_id: int, signal_type: str, confidence: float) -> NewsroomEvent:
    return NewsroomEvent(
        event_type=EventType.SIGNAL_DETECTED.value,
        payload={
            "signal_id": signal_id,
            "signal_type": signal_type,
            "confidence": confidence,
        },
    )


def trend_escalated(*, story_id: int, forecast_probability: float) -> NewsroomEvent:
    return NewsroomEvent(
        event_type=EventType.TREND_ESCALATED.value,
        payload={
            "story_id": story_id,
            "forecast_probability": forecast_probability,
        },
    )


def anomaly_detected(*, anomaly_type: str, scope_key: str, severity: float) -> NewsroomEvent:
    return NewsroomEvent(
        event_type=EventType.ANOMALY_DETECTED.value,
        payload={
            "anomaly_type": anomaly_type,
            "scope_key": scope_key,
            "severity": severity,
        },
    )


def impact_forecast_generated(
    *,
    story_id: int | None,
    signal_id: int | None,
    expected_impact: float,
) -> NewsroomEvent:
    return NewsroomEvent(
        event_type=EventType.IMPACT_FORECAST_GENERATED.value,
        payload={
            "story_id": story_id,
            "signal_id": signal_id,
            "expected_impact": expected_impact,
        },
    )


def priority_decided(
    *,
    pending_news_id: int | None,
    editorial_priority_score: float,
    action: str,
) -> NewsroomEvent:
    return NewsroomEvent(
        event_type=EventType.PRIORITY_DECIDED.value,
        payload={
            "pending_news_id": pending_news_id,
            "editorial_priority_score": editorial_priority_score,
            "action": action,
        },
    )


def policy_changed(*, mode: str, policy_name: str, node_id: str | None = None) -> NewsroomEvent:
    return NewsroomEvent(
        event_type=EventType.POLICY_CHANGED.value,
        payload={"mode": mode, "policy_name": policy_name, "node_id": node_id},
    )


def node_health_changed(
    *,
    node_id: str,
    status: str,
    is_leader: bool,
    reason: str = "",
) -> NewsroomEvent:
    return NewsroomEvent(
        event_type=EventType.NODE_HEALTH_CHANGED.value,
        payload={
            "node_id": node_id,
            "status": status,
            "is_leader": is_leader,
            "reason": reason,
        },
    )


def replay_started(*, run_id: str, from_ts: str, to_ts: str, node_id: str) -> NewsroomEvent:
    return NewsroomEvent(
        event_type=EventType.REPLAY_STARTED.value,
        payload={
            "run_id": run_id,
            "from_ts": from_ts,
            "to_ts": to_ts,
            "node_id": node_id,
        },
    )
