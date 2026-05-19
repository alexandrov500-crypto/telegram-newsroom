from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from bot.distributed.event_bus.security import sign_event_payload, verify_event_payload
from bot.events.types import NewsroomEvent

CURRENT_ENVELOPE_VERSION = 1


@dataclass(frozen=True, slots=True)
class EventEnvelope:
    """Canonical transport-independent event envelope for the newsroom cluster."""

    event_type: str
    payload: dict[str, Any]
    event_id: str = field(default_factory=lambda: uuid4().hex)
    event_version: int = CURRENT_ENVELOPE_VERSION
    causation_id: str | None = None
    correlation_id: str | None = None
    node_id: str = "local"
    region: str = "global"
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )
    partition_key: str = "global"
    signature: str | None = None
    retry_count: int = 0
    trace_id: str | None = None
    span_id: str | None = None

    def with_retry(self) -> EventEnvelope:
        return EventEnvelope(
            event_id=self.event_id,
            event_type=self.event_type,
            payload=dict(self.payload),
            event_version=self.event_version,
            causation_id=self.causation_id,
            correlation_id=self.correlation_id or self.event_id,
            node_id=self.node_id,
            region=self.region,
            timestamp=datetime.now(timezone.utc).isoformat(),
            partition_key=self.partition_key,
            signature=self.signature,
            retry_count=self.retry_count + 1,
            trace_id=self.trace_id,
            span_id=self.span_id,
        )

    def child(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        partition_key: str | None = None,
    ) -> EventEnvelope:
        return EventEnvelope(
            event_type=event_type,
            payload=payload,
            causation_id=self.event_id,
            correlation_id=self.correlation_id or self.event_id,
            node_id=self.node_id,
            region=self.region,
            partition_key=partition_key or self.partition_key,
            trace_id=self.trace_id,
            span_id=self.span_id,
        )

    def to_dict(self, *, sign: bool = True) -> dict[str, Any]:
        body: dict[str, Any] = {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "event_version": self.event_version,
            "causation_id": self.causation_id,
            "correlation_id": self.correlation_id,
            "node_id": self.node_id,
            "region": self.region,
            "timestamp": self.timestamp,
            "partition_key": self.partition_key,
            "payload": dict(self.payload),
            "retry_count": self.retry_count,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
        }
        if sign:
            return sign_event_payload(body)
        if self.signature:
            body["signature"] = self.signature
        return body

    def to_json(self, *, sign: bool = True) -> str:
        return json.dumps(self.to_dict(sign=sign), separators=(",", ":"), default=str)

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, verify_signature: bool = True) -> EventEnvelope:
        payload = dict(data.get("payload") or {})
        if verify_signature and not verify_event_payload(data):
            raise ValueError("event envelope signature invalid")
        return cls(
            event_id=str(data.get("event_id", uuid4().hex)),
            event_type=str(data["event_type"]),
            payload=payload,
            event_version=int(data.get("event_version", CURRENT_ENVELOPE_VERSION)),
            causation_id=data.get("causation_id"),
            correlation_id=data.get("correlation_id"),
            node_id=str(data.get("node_id", "unknown")),
            region=str(data.get("region", "global")),
            timestamp=str(
                data.get("timestamp", datetime.now(timezone.utc).isoformat()),
            ),
            partition_key=str(data.get("partition_key", "global")),
            signature=data.get("signature"),
            retry_count=int(data.get("retry_count", 0)),
            trace_id=data.get("trace_id"),
            span_id=data.get("span_id"),
        )

    @classmethod
    def from_json(cls, raw: str, *, verify_signature: bool = True) -> EventEnvelope:
        return cls.from_dict(json.loads(raw), verify_signature=verify_signature)

    def to_legacy_event(self) -> NewsroomEvent:
        return NewsroomEvent(
            event_id=self.event_id,
            event_type=self.event_type,
            created_at=self.timestamp,
            payload=dict(self.payload),
        )

    @classmethod
    def from_legacy_event(
        cls,
        event: NewsroomEvent,
        *,
        node_id: str = "local",
        region: str = "global",
        partition_key: str = "global",
        correlation_id: str | None = None,
        causation_id: str | None = None,
        trace_id: str | None = None,
        span_id: str | None = None,
    ) -> EventEnvelope:
        return cls(
            event_id=event.event_id,
            event_type=event.event_type,
            payload=dict(event.payload),
            correlation_id=correlation_id,
            causation_id=causation_id,
            node_id=node_id,
            region=region,
            timestamp=event.created_at,
            partition_key=partition_key,
            trace_id=trace_id,
            span_id=span_id,
        )
