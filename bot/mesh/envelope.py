from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from bot.distributed.event_bus.security import sign_event_payload, verify_event_payload

COGNITIVE_ENVELOPE_VERSION = 1


@dataclass(frozen=True, slots=True)
class CognitiveEventEnvelope:
    """Cognitive-layer event — separate from operational EventEnvelope."""

    event_type: str
    payload: dict[str, Any]
    event_id: str = field(default_factory=lambda: uuid4().hex)
    event_version: int = COGNITIVE_ENVELOPE_VERSION
    lane: str = "gossip"
    causation_id: str | None = None
    correlation_id: str | None = None
    node_id: str = "local"
    region: str = "global"
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )
    partition_key: str = "cognitive"
    sequence_num: int = 0
    signature: str | None = None
    ttl_hops: int = 3

    def child(self, event_type: str, payload: dict[str, Any], *, lane: str | None = None) -> CognitiveEventEnvelope:
        return CognitiveEventEnvelope(
            event_type=event_type,
            payload=payload,
            lane=lane or self.lane,
            causation_id=self.event_id,
            correlation_id=self.correlation_id or self.event_id,
            node_id=self.node_id,
            region=self.region,
            partition_key=self.partition_key,
            ttl_hops=max(0, self.ttl_hops - 1),
        )

    def dedup_key(self) -> str:
        return f"{self.event_type}:{self.event_id}"

    def to_dict(self, *, sign: bool = True) -> dict[str, Any]:
        body: dict[str, Any] = {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "event_version": self.event_version,
            "lane": self.lane,
            "causation_id": self.causation_id,
            "correlation_id": self.correlation_id,
            "node_id": self.node_id,
            "region": self.region,
            "timestamp": self.timestamp,
            "partition_key": self.partition_key,
            "sequence_num": self.sequence_num,
            "payload": self.payload,
            "ttl_hops": self.ttl_hops,
        }
        if sign:
            signed = sign_event_payload(body)
            body.update(signed)
        elif self.signature:
            body["signature"] = self.signature
        return body

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, verify: bool = False) -> CognitiveEventEnvelope:
        if verify and not verify_event_payload(data):
            raise ValueError("cognitive envelope signature invalid")
        return cls(
            event_id=str(data["event_id"]),
            event_type=str(data["event_type"]),
            payload=dict(data.get("payload") or {}),
            event_version=int(data.get("event_version", 1)),
            lane=str(data.get("lane", "gossip")),
            causation_id=data.get("causation_id"),
            correlation_id=data.get("correlation_id"),
            node_id=str(data.get("node_id", "local")),
            region=str(data.get("region", "global")),
            timestamp=str(data.get("timestamp", "")),
            partition_key=str(data.get("partition_key", "cognitive")),
            sequence_num=int(data.get("sequence_num", 0)),
            signature=data.get("signature"),
            ttl_hops=int(data.get("ttl_hops", 3)),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(sign=True))
