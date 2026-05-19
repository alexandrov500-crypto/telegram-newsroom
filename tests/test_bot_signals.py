from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from bot.events.bus import EventBus
from bot.events.types import EventType
from bot.signals.anomaly_engine import AnomalyEngine
from bot.signals.correlation_engine import CorrelationEngine
from bot.signals.credibility_engine import CredibilityEngine
from bot.signals.forecasting import forecast_escalation
from bot.signals.impact_analysis import analyze_impact
from bot.signals.priority_engine import compute_editorial_priority
from bot.signals.sentiment_velocity import sentiment_score
from bot.signals.signal_detector import DetectionContext, SignalDetector
from bot.signals.signal_service import SignalIntelligenceService
from bot.signals.types import CredibilityProfile, EditorialAction, ImpactProfile
from bot.storage.db import init_database
from bot.storage.signal_repository import SignalRepository
from bot.storage.source_repository import SourceProfile


def _run(coro):
    return asyncio.run(coro)


class SignalEngineTests(unittest.TestCase):
    def test_geopolitical_signal_detection(self) -> None:
        detector = SignalDetector()
        ctx = DetectionContext(
            title="NATO expands sanctions after missile strike",
            summary="Escalation along the border continues.",
            tags=["nato", "war"],
            entities=["nato", "russia"],
            source="reuters",
            source_count=4,
            cluster_variants=3,
            trend_velocity=0.8,
            importance=0.85,
            novelty=0.6,
            story_id=1,
            cluster_id=10,
            pending_news_id=5,
            topic_acceleration=0.5,
            correlation_velocity=0.55,
        )
        signals = detector.detect(ctx)
        types = {s.type for s in signals}
        self.assertIn("geopolitical_escalation", types)

    def test_impact_and_forecast(self) -> None:
        impact = analyze_impact(
            title="Bitcoin crashes after SEC ETF decision",
            summary="Volatility spikes across crypto markets.",
            tags=["bitcoin", "etf"],
            trend_velocity=0.7,
        )
        self.assertGreater(impact.market_impact, 0.5)
        forecast = forecast_escalation(
            story_id=1,
            importance=0.8,
            trend_velocity=0.75,
            source_count=4,
            novelty=0.6,
            impact=impact,
        )
        self.assertGreater(forecast.forecast_probability, 0.5)

    def test_priority_publish_immediately(self) -> None:
        cred = CredibilityProfile(
            credibility_score=0.85,
            risk_score=0.2,
            sensationalism=0.05,
        )
        decision = compute_editorial_priority(
            importance=0.9,
            novelty=0.7,
            acceleration=0.8,
            credibility=cred,
            forecast_probability=0.82,
            expected_impact=0.88,
            language_count=2,
        )
        self.assertGreater(decision.editorial_priority_score, 0.8)
        self.assertIn(
            decision.action,
            (
                EditorialAction.PUBLISH_IMMEDIATELY.value,
                EditorialAction.ESCALATE_ADMIN.value,
            ),
        )


class SignalPersistenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = init_database(Path(self._tmp.name) / "test.db")
        self.repo = SignalRepository(self.db_path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_baseline_anomaly(self) -> None:
        engine = AnomalyEngine(self.repo, z_threshold=1.5)
        for value in (1.0, 1.2, 1.1, 1.0, 0.9):
            engine.observe_metric(
                scope="topic",
                scope_key="ai",
                metric="activity",
                value=value,
            )
        hit = engine.observe_metric(
            scope="topic",
            scope_key="ai",
            metric="activity",
            value=12.0,
        )
        self.assertIsNotNone(hit)
        assert hit is not None
        self.assertGreater(hit.severity, 0.3)


class SignalServiceIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = init_database(Path(self._tmp.name) / "test.db")
        self.repo = SignalRepository(self.db_path)
        self.service = SignalIntelligenceService(self.repo)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_process_ingest_persists_signals(self) -> None:
        profile = SourceProfile(
            source_name="reuters",
            source_type="rss",
            trust_score=0.85,
            article_count=10,
            accepted_count=8,
            rejected_count=1,
            approval_ratio=0.8,
        )
        decision = _run(
            self.service.process_ingest(
                title="Fed signals rate hike amid inflation fears",
                summary="Markets slide as treasury yields jump.",
                tags=["fed", "inflation"],
                source="reuters",
                source_count=3,
                cluster_variants=2,
                cluster_id=50,
                pending_news_id=99,
                story_id=7,
                importance=0.75,
                novelty=0.65,
                trend_velocity=0.6,
                source_profile=profile,
            )
        )
        self.assertIsNotNone(decision)
        signals = self.repo.list_recent_signals(limit=5)
        self.assertTrue(signals)
        self.assertIsNotNone(decision.editorial_priority_score)


class EventBusTests(unittest.IsolatedAsyncioTestCase):
    async def test_publish_and_dispatch(self) -> None:
        bus = EventBus(max_queue=100)
        bus.start()
        seen: list[str] = []

        async def handler(event) -> None:
            seen.append(event.event_type)

        bus.subscribe(EventType.SIGNAL_DETECTED.value, handler)
        from bot.events.types import signal_detected

        await bus.publish(
            signal_detected(signal_id=1, signal_type="market_moving", confidence=0.9),
        )
        await asyncio.sleep(0.15)
        await bus.stop()
        self.assertIn(EventType.SIGNAL_DETECTED.value, seen)


class CorrelationEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = init_database(Path(self._tmp.name) / "test.db")
        self.repo = SignalRepository(self.db_path)
        self.engine = CorrelationEngine(self.repo)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_multi_source_graph(self) -> None:
        title = "Oil prices surge on Middle East tensions"
        self.engine.record_observation(title=title, source="rss:reuters", entities=["oil"])
        self.engine.record_observation(title=title, source="telegram:channel", entities=["oil"])
        graph = self.engine.record_observation(
            title=title,
            source="rss:bloomberg",
            entities=["oil"],
        )
        self.assertGreaterEqual(len(graph.edges), 1)
