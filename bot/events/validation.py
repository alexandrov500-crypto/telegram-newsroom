from __future__ import annotations

import logging
from typing import Any

from bot.events.envelope import CURRENT_ENVELOPE_VERSION, EventEnvelope
from bot.events.types import EventType

logger = logging.getLogger(__name__)

_REQUIRED_TOP_LEVEL = frozenset(
    {"event_id", "event_type", "event_version", "timestamp", "payload", "node_id"},
)

_KNOWN_TYPES = frozenset(e.value for e in EventType) | frozenset(
    {
        "StoryIngested",
        "StoryEnriched",
        "DigestStarted",
        "DigestCompleted",
        "PublishRequested",
        "PublishCompleted",
        "PublishDuplicateSuppressed",
        "WorkflowCheckpoint",
        "WorkflowFailed",
        "WorkflowRecovered",
        "StoryIngested",
        "StoryClustered",
        "CognitionCompleted",
        "PublishCandidateCreated",
        "PublishApproved",
        "PublishBlocked",
        "PublishDelivered",
        "IncidentCreated",
        "RolloutChanged",
    },
)


class EventValidationError(ValueError):
    pass


def validate_envelope_dict(data: dict[str, Any]) -> None:
    missing = _REQUIRED_TOP_LEVEL - set(data.keys())
    if missing:
        raise EventValidationError(f"missing fields: {sorted(missing)}")
    version = int(data.get("event_version", 0))
    if version > CURRENT_ENVELOPE_VERSION:
        raise EventValidationError(f"unsupported envelope version {version}")
    if str(data["event_type"]) not in _KNOWN_TYPES:
        logger.warning("event=unknown_event_type type=%s", data["event_type"])
    payload = data.get("payload")
    if not isinstance(payload, dict):
        raise EventValidationError("payload must be object")


def validate_envelope(envelope: EventEnvelope) -> None:
    validate_envelope_dict(envelope.to_dict(sign=False))


def is_poison_message(envelope: EventEnvelope, *, max_retries: int = 5) -> bool:
    return envelope.retry_count >= max_retries
