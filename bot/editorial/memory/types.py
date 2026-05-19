from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

FOLLOW_UP_NEW = "new_development"
FOLLOW_UP_FOLLOW = "follow_up"
FOLLOW_UP_DUPLICATE = "duplicate"
FOLLOW_UP_MINOR = "minor_variation"
FOLLOW_UP_HISTORICAL = "historical_context"


@dataclass(frozen=True, slots=True)
class StorylineSnapshot:
    storyline_id: str
    slug: str
    title: str
    topic_keys: tuple[str, ...]
    entity_keys: tuple[str, ...]
    first_seen_at: str
    last_updated_at: str
    publish_count: int
    sources: tuple[str, ...]
    latest_headline: str | None
    latest_summary: str | None
    tone_direction: str | None
    saturation_score: float
    cluster_id: int | None = None


@dataclass(frozen=True, slots=True)
class StoryEventRecord:
    id: int
    storyline_id: str
    pending_news_id: int | None
    event_type: str
    follow_up_kind: str
    headline: str
    summary: str | None
    source: str | None
    context_snippet: str | None
    contradiction_flags: tuple[str, ...]
    novelty_score: float
    created_at: str


@dataclass(frozen=True, slots=True)
class EditorialMemoryReport:
    storyline_id: str | None = None
    storyline_title: str | None = None
    follow_up_kind: str = FOLLOW_UP_NEW
    context_snippet: str | None = None
    warnings: tuple[str, ...] = ()
    saturation_score: float = 0.0
    contradiction_flags: tuple[str, ...] = ()
    publish_count: int = 0
    match_score: float = 0.0
    framing_hint: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
