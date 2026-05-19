from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from bot.events.envelope import EventEnvelope


class LiveEventType(str, Enum):
    STORY_INGESTED = "StoryIngested"
    STORY_CLUSTERED = "StoryClustered"
    COGNITION_COMPLETED = "CognitionCompleted"
    PUBLISH_CANDIDATE_CREATED = "PublishCandidateCreated"
    PUBLISH_APPROVED = "PublishApproved"
    PUBLISH_BLOCKED = "PublishBlocked"
    PUBLISH_DELIVERED = "PublishDelivered"
    INCIDENT_CREATED = "IncidentCreated"
    ROLLOUT_CHANGED = "RolloutChanged"


@dataclass(frozen=True)
class LiveEventContract:
    event_type: LiveEventType
    schema_version: int = 1
    required_fields: frozenset[str] = frozenset()

    def validate_payload(self, payload: dict[str, Any]) -> None:
        missing = self.required_fields - set(payload.keys())
        if missing:
            raise ValueError(f"{self.event_type.value} missing: {sorted(missing)}")


_CONTRACTS: dict[LiveEventType, LiveEventContract] = {
    LiveEventType.STORY_INGESTED: LiveEventContract(
        LiveEventType.STORY_INGESTED, required_fields=frozenset({"story_id", "source"}),
    ),
    LiveEventType.STORY_CLUSTERED: LiveEventContract(
        LiveEventType.STORY_CLUSTERED, required_fields=frozenset({"story_id", "cluster_id"}),
    ),
    LiveEventType.COGNITION_COMPLETED: LiveEventContract(
        LiveEventType.COGNITION_COMPLETED,
        required_fields=frozenset({"story_id", "confidence", "duration_ms"}),
    ),
    LiveEventType.PUBLISH_CANDIDATE_CREATED: LiveEventContract(
        LiveEventType.PUBLISH_CANDIDATE_CREATED,
        required_fields=frozenset({"pending_news_id", "channel_id"}),
    ),
    LiveEventType.PUBLISH_APPROVED: LiveEventContract(
        LiveEventType.PUBLISH_APPROVED,
        required_fields=frozenset({"pending_news_id", "operator_id"}),
    ),
    LiveEventType.PUBLISH_BLOCKED: LiveEventContract(
        LiveEventType.PUBLISH_BLOCKED,
        required_fields=frozenset({"pending_news_id", "reason"}),
    ),
    LiveEventType.PUBLISH_DELIVERED: LiveEventContract(
        LiveEventType.PUBLISH_DELIVERED,
        required_fields=frozenset({"pending_news_id", "channel_id", "message_id"}),
    ),
    LiveEventType.INCIDENT_CREATED: LiveEventContract(
        LiveEventType.INCIDENT_CREATED,
        required_fields=frozenset({"incident_id", "severity"}),
    ),
    LiveEventType.ROLLOUT_CHANGED: LiveEventContract(
        LiveEventType.ROLLOUT_CHANGED,
        required_fields=frozenset({"stage", "previous_stage"}),
    ),
}


def build_envelope(
    event_type: LiveEventType,
    payload: dict[str, Any],
    *,
    node_id: str = "local",
    region: str = "global",
    correlation_id: str | None = None,
    causation_id: str | None = None,
    partition_key: str | None = None,
) -> EventEnvelope:
    contract = _CONTRACTS[event_type]
    contract.validate_payload(payload)
    return EventEnvelope(
        event_type=event_type.value,
        payload=payload,
        node_id=node_id,
        region=region,
        correlation_id=correlation_id,
        causation_id=causation_id,
        partition_key=partition_key or str(payload.get("channel_id", "global")),
    )
