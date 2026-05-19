from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class StoryStatus(str, Enum):
    CREATED = "created"
    ACTIVE = "active"
    TRENDING = "trending"
    COOLDOWN = "cooldown"
    ARCHIVED = "archived"


class StoryEventType(str, Enum):
    UPDATE = "update"
    ESCALATION = "escalation"
    REVERSAL = "reversal"
    MILESTONE = "milestone"
    CONTRADICTION = "contradiction"
    SHIFT = "shift"


class TrendPhase(str, Enum):
    BREAKING = "breaking"
    VIRAL = "viral"
    COOLING_DOWN = "cooling_down"
    RESURFACING = "resurfacing"
    STABLE = "stable"


@dataclass(frozen=True, slots=True)
class StoryEvent:
    type: str
    significance: float
    headline: str
    summary: str | None = None
    pending_news_id: int | None = None
    cluster_id: int | None = None


@dataclass(frozen=True, slots=True)
class StorySnapshot:
    id: int
    title: str
    canonical_summary: str | None
    status: str
    importance_score: float
    novelty_score: float
    trend_velocity: float
    geopolitical_tags: tuple[str, ...]
    languages_json: str | None
    fingerprint_storage: str | None
    first_seen_at: str
    last_updated_at: str
    cluster_count: int = 0
    source_count: int = 0
    entity_names: tuple[str, ...] = ()


@dataclass
class StoryMatchCandidate:
    story: StorySnapshot
    embedding_similarity: float
    entity_overlap: float
    recency_score: float

    @property
    def match_score(self) -> float:
        return (
            self.embedding_similarity * 0.5
            + self.entity_overlap * 0.3
            + self.recency_score * 0.2
        )


@dataclass
class ImportanceBreakdown:
    importance_score: float
    source_trust: float
    corroboration: float
    entity_weight: float
    geopolitical: float
    market_impact: float
    trend_velocity: float
    language_spread: float
    cluster_growth: float


@dataclass
class NoveltyBreakdown:
    novelty_score: float
    update_delta_score: float
    redundancy_score: float
