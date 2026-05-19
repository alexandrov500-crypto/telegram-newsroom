from __future__ import annotations

import re
from dataclasses import dataclass

from bot.signals.sentiment_velocity import detect_sentiment_regime, sentiment_score
from bot.signals.types import Signal, SignalType

_GEO_ESCALATION = re.compile(
    r"\b(war|invasion|missile|mobiliz|sanction|nato|strike|ceasefire|border)\b",
    re.I,
)
_MARKET = re.compile(
    r"\b(etf|fed|crash|surge|bitcoin|ethereum|sec|default|bank run)\b",
    re.I,
)


@dataclass(frozen=True)
class DetectionContext:
    title: str
    summary: str | None
    tags: list[str]
    entities: list[str]
    source: str | None
    source_count: int
    cluster_variants: int
    trend_velocity: float
    importance: float
    novelty: float
    story_id: int | None
    cluster_id: int | None
    pending_news_id: int | None
    topic_acceleration: float = 0.0
    correlation_velocity: float = 0.0
    sentiment_velocity: float = 0.0
    previous_sentiment: float = 0.0


class SignalDetector:
    """Extract editorial signals from ingest context."""

    def detect(self, ctx: DetectionContext) -> list[Signal]:
        text = f"{ctx.title} {ctx.summary or ''}"
        entity_tuple = tuple(ctx.entities[:8])
        signals: list[Signal] = []

        current_sentiment = sentiment_score(text)
        regime = detect_sentiment_regime(text, velocity=ctx.sentiment_velocity)
        if regime == "panic" or (
            ctx.previous_sentiment > 0.1 and current_sentiment < -0.25
        ):
            signals.append(
                Signal(
                    type=SignalType.SENTIMENT_INVERSION.value,
                    confidence=min(0.95, 0.65 + abs(ctx.sentiment_velocity)),
                    entities=entity_tuple,
                    velocity_score=abs(ctx.sentiment_velocity),
                    title=ctx.title,
                    summary=ctx.summary,
                    story_id=ctx.story_id,
                    cluster_id=ctx.cluster_id,
                    pending_news_id=ctx.pending_news_id,
                    source=ctx.source,
                ),
            )

        if ctx.topic_acceleration >= 0.55:
            signals.append(
                Signal(
                    type=SignalType.TOPIC_SPIKE.value,
                    confidence=min(0.95, 0.5 + ctx.topic_acceleration * 0.45),
                    entities=entity_tuple,
                    velocity_score=ctx.topic_acceleration,
                    title=ctx.title,
                    summary=ctx.summary,
                    story_id=ctx.story_id,
                    cluster_id=ctx.cluster_id,
                    pending_news_id=ctx.pending_news_id,
                    source=ctx.source,
                ),
            )

        if _GEO_ESCALATION.search(text):
            conf = min(0.98, 0.7 + ctx.trend_velocity * 0.2 + ctx.importance * 0.1)
            signals.append(
                Signal(
                    type=SignalType.GEOPOLITICAL_ESCALATION.value,
                    confidence=conf,
                    entities=entity_tuple,
                    velocity_score=ctx.trend_velocity,
                    title=ctx.title,
                    summary=ctx.summary,
                    story_id=ctx.story_id,
                    cluster_id=ctx.cluster_id,
                    pending_news_id=ctx.pending_news_id,
                    source=ctx.source,
                ),
            )

        if _MARKET.search(text):
            signals.append(
                Signal(
                    type=SignalType.MARKET_MOVING.value,
                    confidence=min(0.95, 0.68 + ctx.importance * 0.15),
                    entities=entity_tuple,
                    velocity_score=ctx.trend_velocity,
                    title=ctx.title,
                    summary=ctx.summary,
                    story_id=ctx.story_id,
                    cluster_id=ctx.cluster_id,
                    pending_news_id=ctx.pending_news_id,
                    source=ctx.source,
                ),
            )

        if ctx.source_count >= 3 and ctx.correlation_velocity >= 0.4:
            signals.append(
                Signal(
                    type=SignalType.CROSS_SOURCE_PROPAGATION.value,
                    confidence=min(0.95, 0.55 + ctx.source_count * 0.08),
                    entities=entity_tuple,
                    velocity_score=ctx.correlation_velocity,
                    title=ctx.title,
                    summary=ctx.summary,
                    story_id=ctx.story_id,
                    cluster_id=ctx.cluster_id,
                    pending_news_id=ctx.pending_news_id,
                    source=ctx.source,
                ),
            )

        if ctx.trend_velocity >= 0.65 and ctx.novelty >= 0.45:
            signals.append(
                Signal(
                    type=SignalType.NARRATIVE_ACCELERATION.value,
                    confidence=min(0.95, ctx.trend_velocity * 0.85 + ctx.novelty * 0.1),
                    entities=entity_tuple,
                    velocity_score=ctx.trend_velocity,
                    title=ctx.title,
                    summary=ctx.summary,
                    story_id=ctx.story_id,
                    cluster_id=ctx.cluster_id,
                    pending_news_id=ctx.pending_news_id,
                    source=ctx.source,
                ),
            )

        if ctx.source_count >= 4 and ctx.cluster_variants >= 3:
            signals.append(
                Signal(
                    type=SignalType.COORDINATED_NARRATIVE.value,
                    confidence=min(0.92, 0.5 + ctx.source_count * 0.09),
                    entities=entity_tuple,
                    velocity_score=ctx.correlation_velocity,
                    title=ctx.title,
                    summary=ctx.summary,
                    story_id=ctx.story_id,
                    cluster_id=ctx.cluster_id,
                    pending_news_id=ctx.pending_news_id,
                    source=ctx.source,
                ),
            )

        if len(ctx.entities) >= 2:
            entity_activity = min(1.0, len(ctx.entities) / 6.0 + ctx.cluster_variants * 0.08)
            if entity_activity >= 0.55:
                signals.append(
                    Signal(
                        type=SignalType.ENTITY_SURGE.value,
                        confidence=min(0.9, 0.45 + entity_activity * 0.4),
                        entities=entity_tuple,
                        velocity_score=entity_activity,
                        title=ctx.title,
                        summary=ctx.summary,
                        story_id=ctx.story_id,
                        cluster_id=ctx.cluster_id,
                        pending_news_id=ctx.pending_news_id,
                        source=ctx.source,
                    ),
                )

        return signals
