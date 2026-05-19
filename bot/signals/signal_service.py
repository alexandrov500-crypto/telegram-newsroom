from __future__ import annotations

import logging
import time

from bot.events.types import (
    anomaly_detected,
    impact_forecast_generated,
    priority_decided,
    signal_detected,
    trend_escalated,
)
from bot.signals.anomaly_engine import AnomalyEngine
from bot.signals.correlation_engine import CorrelationEngine
from bot.signals.credibility_engine import CredibilityEngine
from bot.signals.cross_market_signals import detect_cross_market_signals
from bot.signals.forecasting import forecast_escalation
from bot.signals.impact_analysis import analyze_impact
from bot.signals.priority_engine import compute_editorial_priority
from bot.signals.sentiment_velocity import sentiment_score, sentiment_velocity
from bot.signals.signal_detector import DetectionContext, SignalDetector
from bot.signals.topic_acceleration import TopicAcceleration, topic_key_from_tags
from bot.signals.types import PriorityDecision, Signal
from bot.storage.entity_repository import EntityRepository
from bot.storage.signal_repository import SignalRepository
from bot.storage.source_repository import SourceProfile, SourceRepository
from bot.storage.story_repository import StoryRepository

logger = logging.getLogger(__name__)


class SignalIntelligenceService:
    """Orchestrates real-time signal detection and prioritization."""

    def __init__(
        self,
        signal_repo: SignalRepository,
        *,
        story_repo: StoryRepository | None = None,
        sources: SourceRepository | None = None,
        entities: EntityRepository | None = None,
        event_bus: object | None = None,
    ) -> None:
        self._repo = signal_repo
        self._story_repo = story_repo
        self._sources = sources
        self._entities = entities
        self._bus = event_bus
        self._detector = SignalDetector()
        self._anomaly = AnomalyEngine(signal_repo)
        self._correlation = CorrelationEngine(signal_repo)
        self._credibility = CredibilityEngine(signal_repo)
        self._topics = TopicAcceleration(signal_repo)

    @property
    def repository(self) -> SignalRepository:
        return self._repo

    async def process_ingest(
        self,
        *,
        title: str,
        summary: str | None,
        tags: list[str],
        source: str | None,
        source_count: int,
        cluster_variants: int,
        cluster_id: int | None,
        pending_news_id: int | None,
        story_id: int | None,
        importance: float,
        novelty: float,
        trend_velocity: float,
        languages: list[str] | None = None,
        source_profile: SourceProfile | None = None,
    ) -> PriorityDecision | None:
        started = time.perf_counter()
        try:
            return await self._process_ingest_sync(
                title=title,
                summary=summary,
                tags=tags,
                source=source,
                source_count=source_count,
                cluster_variants=cluster_variants,
                cluster_id=cluster_id,
                pending_news_id=pending_news_id,
                story_id=story_id,
                importance=importance,
                novelty=novelty,
                trend_velocity=trend_velocity,
                languages=languages,
                source_profile=source_profile,
            )
        except Exception:
            logger.exception(
                "event=signal_intelligence_failed pending_news_id=%s cluster_id=%s",
                pending_news_id,
                cluster_id,
            )
            return None
        finally:
            elapsed = time.perf_counter() - started
            from bot.observability.metrics import observe_signal_detection

            observe_signal_detection(elapsed)

    async def _process_ingest_sync(
        self,
        **kwargs: object,
    ) -> PriorityDecision | None:
        title = str(kwargs["title"])
        summary = kwargs.get("summary")  # type: ignore[assignment]
        tags = list(kwargs.get("tags") or [])  # type: ignore[arg-type]
        source = kwargs.get("source")  # type: ignore[assignment]
        source_count = int(kwargs.get("source_count") or 1)  # type: ignore[arg-type]
        cluster_variants = int(kwargs.get("cluster_variants") or 1)  # type: ignore[arg-type]
        cluster_id = kwargs.get("cluster_id")  # type: ignore[assignment]
        pending_news_id = kwargs.get("pending_news_id")  # type: ignore[assignment]
        story_id = kwargs.get("story_id")  # type: ignore[assignment]
        importance = float(kwargs.get("importance") or 0.5)  # type: ignore[arg-type]
        novelty = float(kwargs.get("novelty") or 0.5)  # type: ignore[arg-type]
        trend_velocity = float(kwargs.get("trend_velocity") or 0.0)  # type: ignore[arg-type]
        languages = list(kwargs.get("languages") or ["en"])  # type: ignore[arg-type]
        source_profile = kwargs.get("source_profile")  # type: ignore[assignment]

        entity_names: list[str] = []
        if pending_news_id and self._entities:
            entity_names = self._entities.get_entity_names_for_pending(
                int(pending_news_id),
                limit=10,
            )
        if not entity_names:
            entity_names = [t.lstrip("#") for t in tags[:6]]

        topic = topic_key_from_tags(tags)
        topic_accel, _ = self._topics.record_and_score(
            topic=topic,
            cluster_variants=cluster_variants,
            source_count=source_count,
        )

        graph = self._correlation.record_observation(
            title=title,
            source=str(source) if source else None,
            entities=entity_names,
        )

        text = f"{title} {summary or ''}"
        current_sentiment = sentiment_score(text)
        scope_key = str(story_id or cluster_id or topic)
        prev_velocity = self._repo.recent_sentiment_velocity(scope_key)
        sent_vel = sentiment_velocity(prev_velocity, current_sentiment)
        self._repo.save_sentiment_window(
            scope="story",
            scope_key=scope_key,
            sentiment_score=current_sentiment,
            velocity=sent_vel,
        )

        if source_profile is None and self._sources and source:
            source_profile = self._sources.get_profile(str(source))
        elif source_profile is None:
            from bot.storage.source_repository import SourceProfile as SP

            source_profile = SP(
                source_name=str(source or "unknown"),
                source_type="unknown",
                trust_score=0.5,
                article_count=0,
                accepted_count=0,
                rejected_count=0,
                approval_ratio=0.5,
            )

        cred = self._credibility.evaluate(
            profile=source_profile,
            title=title,
            summary=str(summary) if summary else None,
        )

        impact = analyze_impact(
            title=title,
            summary=str(summary) if summary else None,
            tags=tags,
            trend_velocity=trend_velocity,
        )

        forecast = forecast_escalation(
            story_id=int(story_id) if story_id else None,
            importance=importance,
            trend_velocity=trend_velocity,
            source_count=source_count,
            novelty=novelty,
            impact=impact,
            correlation_velocity=graph.amplification_velocity,
        )
        forecast_id = self._repo.save_forecast(forecast)

        ctx = DetectionContext(
            title=title,
            summary=str(summary) if summary else None,
            tags=tags,
            entities=entity_names,
            source=str(source) if source else None,
            source_count=source_count,
            cluster_variants=cluster_variants,
            trend_velocity=trend_velocity,
            importance=importance,
            novelty=novelty,
            story_id=int(story_id) if story_id else None,
            cluster_id=int(cluster_id) if cluster_id else None,
            pending_news_id=int(pending_news_id) if pending_news_id else None,
            topic_acceleration=topic_accel,
            correlation_velocity=graph.amplification_velocity,
            sentiment_velocity=sent_vel,
            previous_sentiment=prev_velocity,
        )
        signals = self._detector.detect(ctx)

        entity_centrality = min(1.0, len(entity_names) / 8.0)
        priority = compute_editorial_priority(
            importance=importance,
            novelty=novelty,
            acceleration=max(topic_accel, trend_velocity),
            credibility=cred,
            forecast_probability=forecast.forecast_probability,
            expected_impact=forecast.expected_impact,
            language_count=len(languages),
            entity_centrality=entity_centrality,
        )

        cross_market = detect_cross_market_signals(text, velocity=trend_velocity)
        if cross_market:
            priority = PriorityDecision(
                editorial_priority_score=min(
                    1.0,
                    priority.editorial_priority_score + 0.05,
                ),
                action=priority.action,
                reason=priority.reason + "+cross_market",
            )

        for signal in signals:
            sid = self._persist_signal(
                signal,
                impact=impact,
                forecast=forecast,
                priority=priority,
            )
            await self._emit(signal_detected(signal_id=sid, signal_type=signal.type, confidence=signal.confidence))

        await self._emit(
            impact_forecast_generated(
                story_id=int(story_id) if story_id else None,
                signal_id=None,
                expected_impact=forecast.expected_impact,
            ),
        )

        if forecast.forecast_probability >= 0.72 and story_id:
            from bot.observability.metrics import record_forecast_escalation

            record_forecast_escalation()
            await self._emit(
                trend_escalated(
                    story_id=int(story_id),
                    forecast_probability=forecast.forecast_probability,
                ),
            )

        await self._check_anomalies(
            topic=topic,
            scope_key=scope_key,
            source_count=source_count,
            graph_sources=[e.source_a for e in graph.edges] + [e.source_b for e in graph.edges],
            prev_sentiment=prev_velocity,
            current_sentiment=current_sentiment,
        )

        await self._emit(
            priority_decided(
                pending_news_id=int(pending_news_id) if pending_news_id else None,
                editorial_priority_score=priority.editorial_priority_score,
                action=priority.action,
            ),
        )

        from bot.observability.metrics import record_signal_detected

        if signals:
            record_signal_detected(len(signals))

        _ = forecast_id
        return priority

    def _persist_signal(
        self,
        signal: Signal,
        *,
        impact: object,
        forecast: object,
        priority: PriorityDecision,
    ) -> int:
        from bot.signals.types import ImpactProfile, TrendForecast

        return self._repo.save_signal(
            signal,
            impact=impact if isinstance(impact, ImpactProfile) else None,
            forecast=forecast if isinstance(forecast, TrendForecast) else None,
            priority_score=priority.editorial_priority_score,
            editorial_action=priority.action,
        )

    async def _check_anomalies(
        self,
        *,
        topic: str,
        scope_key: str,
        source_count: int,
        graph_sources: list[str],
        prev_sentiment: float,
        current_sentiment: float,
    ) -> None:
        hit = self._anomaly.observe_metric(
            scope="topic",
            scope_key=topic,
            metric="mentions",
            value=float(source_count),
        )
        if hit:
            self._repo.save_anomaly(
                anomaly_type=hit.anomaly_type,
                scope=hit.scope,
                scope_key=hit.scope_key,
                severity=hit.severity,
                baseline_value=hit.baseline,
                observed_value=hit.observed,
                detail=hit.detail,
            )
            from bot.observability.metrics import record_anomaly_detected

            record_anomaly_detected(hit.anomaly_type)
            await self._emit(
                anomaly_detected(
                    anomaly_type=hit.anomaly_type,
                    scope_key=hit.scope_key,
                    severity=hit.severity,
                ),
            )

        sync = self._anomaly.detect_source_sync(
            narrative_key=scope_key,
            sources_in_window=graph_sources or [f"src_{source_count}"],
        )
        if sync:
            self._repo.save_anomaly(
                anomaly_type=sync.anomaly_type,
                scope=sync.scope,
                scope_key=sync.scope_key,
                severity=sync.severity,
                baseline_value=sync.baseline,
                observed_value=sync.observed,
                detail=sync.detail,
            )

        collapse = self._anomaly.detect_sentiment_collapse(
            scope_key=scope_key,
            previous_sentiment=prev_sentiment,
            current_sentiment=current_sentiment,
        )
        if collapse:
            self._repo.save_anomaly(
                anomaly_type=collapse.anomaly_type,
                scope=collapse.scope,
                scope_key=collapse.scope_key,
                severity=collapse.severity,
                baseline_value=collapse.baseline,
                observed_value=collapse.observed,
                detail=collapse.detail,
            )

    async def _emit(self, event: object) -> None:
        if self._bus is None:
            return
        try:
            await self._bus.publish(event)  # type: ignore[attr-defined]
        except Exception:
            logger.exception("event=signal_bus_publish_failed")

    def maintenance_pass(self) -> int:
        return self._repo.prune_old_signals(days=30)
