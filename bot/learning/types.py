from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class OutcomeLabel(str, Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    FALSE_POSITIVE = "false_positive"
    MISSED_ESCALATION = "missed_escalation"
    LOW_VALUE = "low_value"


@dataclass(frozen=True, slots=True)
class EditorialOutcome:
    outcome_type: str
    label: str
    score: float
    pending_news_id: int | None = None
    story_id: int | None = None
    signal_id: int | None = None
    source: str | None = None
    detail: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FeedbackSignal:
    kind: str
    weight: float
    target: str
    detail: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DecisionEvaluation:
    correct: bool
    expected_action: str | None
    actual_action: str
    confidence: float


@dataclass(frozen=True, slots=True)
class LearningScores:
    signal_precision_score: float
    forecast_reliability_score: float
    agent_accuracy_score: float
    publish_effectiveness_score: float
    signal_to_noise_ratio: float


@dataclass(frozen=True, slots=True)
class AgentPerformanceSnapshot:
    agent_name: str
    accuracy: float
    latency_ms: float
    usefulness: float
    false_positive_rate: float
    escalation_success: float
    publish_success: float


@dataclass(frozen=True, slots=True)
class DecisionAudit:
    action: str
    reason: list[str]
    scores: dict[str, float]
    policy: str
    pending_news_id: int | None = None
    story_id: int | None = None
    signal_id: int | None = None
