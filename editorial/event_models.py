"""Typed structures for event/topic intelligence (serializable dicts)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(slots=True)
class EventIdentity:
    """Stable identity for a cluster-derived event."""

    fingerprint: str
    topic_hint: str
    channel_keys: tuple[str, ...]
    first_seen_unix: float
    last_seen_unix: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "fingerprint": self.fingerprint,
            "topic_hint": self.topic_hint,
            "channel_keys": list(self.channel_keys),
            "first_seen_unix": self.first_seen_unix,
            "last_seen_unix": self.last_seen_unix,
        }


@dataclass(slots=True)
class EventCluster:
    """Snapshot of a clustered raw-post set at scoring time."""

    fingerprint: str
    post_ids: tuple[int, ...]
    size: int
    cohesion: float

    def to_dict(self) -> dict[str, Any]:
        return {"fingerprint": self.fingerprint, "post_ids": list(self.post_ids), "size": self.size, "cohesion": self.cohesion}


@dataclass(slots=True)
class EventEvolution:
    """Update-vs-new classification + continuity."""

    kind: Literal["new", "update", "ambiguous"]
    continuity_score: float
    related_fingerprint: str | None
    reasons: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "continuity_score": round(self.continuity_score, 4),
            "related_fingerprint": self.related_fingerprint,
            "reasons": list(self.reasons),
        }


def event_evolution_from_dict(d: dict[str, Any]) -> EventEvolution:
    k = str(d.get("kind") or "ambiguous")
    if k not in ("new", "update", "ambiguous"):
        k = "ambiguous"
    return EventEvolution(
        kind=k,  # type: ignore[arg-type]
        continuity_score=float(d.get("continuity_score") or 0.0),
        related_fingerprint=str(d.get("related_fingerprint") or "") or None,
        reasons=tuple(str(x) for x in (d.get("reasons") or []) if x),
    )
