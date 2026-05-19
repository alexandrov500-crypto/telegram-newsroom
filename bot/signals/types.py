from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SignalType(str, Enum):
    TOPIC_SPIKE = "topic_spike"
    ENTITY_SURGE = "entity_surge"
    GEOPOLITICAL_ESCALATION = "geopolitical_escalation"
    MARKET_MOVING = "market_moving"
    CROSS_SOURCE_PROPAGATION = "cross_source_propagation"
    SENTIMENT_INVERSION = "sentiment_inversion"
    NARRATIVE_ACCELERATION = "narrative_acceleration"
    COORDINATED_NARRATIVE = "coordinated_narrative"
    ANOMALY_VOLUME = "anomaly_volume"


class EditorialAction(str, Enum):
    PUBLISH_IMMEDIATELY = "publish_immediately"
    WAIT_CONFIRMATION = "wait_confirmation"
    ESCALATE_ADMIN = "escalate_admin"
    DIGEST_ONLY = "digest_only"
    SUPPRESS = "suppress"


class AnomalyType(str, Enum):
    VOLUME_SPIKE = "volume_spike"
    COORDINATED_POSTING = "coordinated_posting"
    SOURCE_SYNC = "source_sync"
    SENTIMENT_COLLAPSE = "sentiment_collapse"
    ENTITY_FREQUENCY = "entity_frequency"


@dataclass(frozen=True, slots=True)
class Signal:
    type: str
    confidence: float
    entities: tuple[str, ...] = ()
    velocity_score: float = 0.0
    title: str = ""
    summary: str | None = None
    story_id: int | None = None
    cluster_id: int | None = None
    pending_news_id: int | None = None
    source: str | None = None


@dataclass(frozen=True, slots=True)
class ImpactProfile:
    market_impact: float = 0.0
    geopolitical_impact: float = 0.0
    technological_impact: float = 0.0
    social_impact: float = 0.0
    cyber_risk: float = 0.0
    ai_ecosystem_impact: float = 0.0

    @property
    def composite(self) -> float:
        return max(
            self.market_impact,
            self.geopolitical_impact,
            self.technological_impact,
            self.social_impact,
            self.cyber_risk,
            self.ai_ecosystem_impact,
        )


@dataclass(frozen=True, slots=True)
class TrendForecast:
    forecast_probability: float
    expected_impact: float
    expected_reach: float
    story_id: int | None = None


@dataclass(frozen=True, slots=True)
class CredibilityProfile:
    credibility_score: float
    risk_score: float
    bias_profile: dict[str, float] = field(default_factory=dict)
    sensationalism: float = 0.0


@dataclass(frozen=True, slots=True)
class PriorityDecision:
    editorial_priority_score: float
    action: str
    reason: str
