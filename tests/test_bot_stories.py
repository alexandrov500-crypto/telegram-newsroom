from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from bot.editorial.digest_ranker import DigestRanker, classify_story
from bot.editorial.importance import compute_importance, importance_tier
from bot.editorial.narrative_detector import pick_best_story_match, score_story_match
from bot.editorial.novelty import compute_novelty
from bot.editorial.story_evolution import detect_story_event, is_escalation
from bot.editorial.story_memory import StoryMemoryService
from bot.editorial.story_types import StorySnapshot, StoryStatus
from bot.editorial.timeline import compact_timeline_lines
from bot.processing.semantic import build_fingerprint, tokens_to_storage
from bot.storage.db import init_database
from bot.storage.story_repository import StoryRepository, StoryTimelineEntry


def _run(coro):
    return asyncio.run(coro)


class StoryRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = init_database(Path(self._tmp.name) / "test.db")
        self.repo = StoryRepository(self.db_path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_create_and_timeline(self) -> None:
        story_id = self.repo.create_story(
            title="SEC approves Ethereum ETF",
            canonical_summary="Regulators cleared spot ETH funds.",
            status=StoryStatus.ACTIVE.value,
            importance_score=0.88,
        )
        self.repo.add_event(
            story_id=story_id,
            event_type="milestone",
            significance=0.9,
            headline="ETF officially approved",
            summary="Trading may begin next week.",
        )
        story = self.repo.get_story(story_id)
        assert story is not None
        self.assertEqual(story.title, "SEC approves Ethereum ETF")
        timeline = self.repo.timeline(story_id)
        self.assertEqual(len(timeline), 1)
        lines = compact_timeline_lines(timeline)
        self.assertTrue(any("ETF" in line for line in lines))

    def test_cluster_link_and_lookup(self) -> None:
        story_id = self.repo.create_story(
            title="Market volatility",
            canonical_summary=None,
        )
        self.repo.link_cluster(story_id=story_id, cluster_id=42, pending_news_id=7)
        self.assertEqual(self.repo.story_id_for_cluster(42), story_id)


class NarrativeScoringTests(unittest.TestCase):
    def test_match_score_weights(self) -> None:
        fp, _ = build_fingerprint("Ethereum ETF approval expected")
        candidate = StorySnapshot(
            id=1,
            title="Ethereum ETF approval expected",
            canonical_summary="SEC review ongoing",
            status="active",
            importance_score=0.7,
            novelty_score=0.5,
            trend_velocity=0.4,
            geopolitical_tags=(),
            languages_json=None,
            fingerprint_storage=tokens_to_storage(fp),
            first_seen_at="2026-05-15T10:00:00+00:00",
            last_updated_at="2026-05-15T12:00:00+00:00",
            entity_names=("ethereum", "sec"),
        )
        scored = score_story_match(
            title="SEC approves Ethereum ETF",
            entity_keys={"ethereum", "sec"},
            candidate=candidate,
        )
        self.assertGreater(scored.match_score, 0.4)

    def test_pick_best_story_match(self) -> None:
        fp, _ = build_fingerprint("Russia sanctions expanded")
        candidate = StorySnapshot(
            id=2,
            title="Russia sanctions expanded",
            canonical_summary=None,
            status="active",
            importance_score=0.8,
            novelty_score=0.6,
            trend_velocity=0.5,
            geopolitical_tags=("sanction",),
            languages_json=None,
            fingerprint_storage=tokens_to_storage(fp),
            first_seen_at="2026-05-14T10:00:00+00:00",
            last_updated_at="2026-05-15T11:00:00+00:00",
            entity_names=("russia",),
        )
        matched, score = pick_best_story_match(
            title="New sanctions on Russia announced",
            entity_keys={"russia"},
            candidates=[candidate],
        )
        self.assertIsNotNone(matched)
        self.assertGreater(score, 0.5)


class EditorialEngineTests(unittest.TestCase):
    def test_importance_tiers(self) -> None:
        result = compute_importance(
            title="Fed raises rates amid inflation",
            summary="Markets reacted sharply.",
            tags=["fed", "rates"],
            source_trust=0.8,
            source_count=3,
            entity_names=["federal reserve"],
            trend_velocity=0.6,
            language_count=2,
            cluster_variant_count=4,
        )
        self.assertGreaterEqual(result.importance_score, 0.5)
        self.assertEqual(importance_tier(0.92), "breaking_global")

    def test_novelty_reduces_on_repeat(self) -> None:
        first = compute_novelty(
            title="Breaking: ceasefire talks",
            summary="Diplomats meet in Geneva.",
            prior_title=None,
            prior_summary=None,
            cluster_variant_count=1,
        )
        second = compute_novelty(
            title="Breaking: ceasefire talks continue",
            summary="Diplomats meet in Geneva.",
            prior_title="Breaking: ceasefire talks",
            prior_summary="Diplomats meet in Geneva.",
            cluster_variant_count=2,
        )
        self.assertGreater(first.novelty_score, second.novelty_score)

    def test_escalation_detection(self) -> None:
        event = detect_story_event(
            title="Missile strike escalates conflict",
            summary="Casualties reported near border.",
            prior_summary="Tensions were high.",
            importance_delta=0.2,
        )
        self.assertTrue(is_escalation(event.type))

    def test_digest_classification(self) -> None:
        story = StorySnapshot(
            id=3,
            title="NVIDIA unveils new AI chip",
            canonical_summary="Semiconductor rally continues.",
            status="active",
            importance_score=0.7,
            novelty_score=0.6,
            trend_velocity=0.5,
            geopolitical_tags=(),
            languages_json=None,
            fingerprint_storage=None,
            first_seen_at="2026-05-15T10:00:00+00:00",
            last_updated_at="2026-05-15T12:00:00+00:00",
        )
        self.assertEqual(classify_story(story), "tech_ai")


class StoryMemoryIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = init_database(Path(self._tmp.name) / "test.db")
        self.repo = StoryRepository(self.db_path)
        self.memory = StoryMemoryService(self.repo)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_process_cluster_creates_story(self) -> None:
        story_id = _run(
            self.memory.process_cluster_update(
                title="Bitcoin volatility spikes after ETF news",
                summary="Traders reposition as flows increase.",
                tags=["bitcoin", "etf"],
                cluster_id=100,
                pending_news_id=1,
                source="reuters",
                source_trust=0.85,
                source_count=2,
                cluster_variant_count=2,
                priority_score=0.7,
                languages=["en"],
            )
        )
        self.assertIsNotNone(story_id)
        story = self.repo.get_story(int(story_id))
        assert story is not None
        self.assertGreater(story.importance_score, 0.4)
        self.assertEqual(self.repo.story_id_for_cluster(100), story_id)

    def test_process_cluster_updates_existing(self) -> None:
        first_id = _run(
            self.memory.process_cluster_update(
                title="Ukraine ceasefire talks begin",
                summary="Delegates arrive in Istanbul.",
                tags=["ukraine", "ceasefire"],
                cluster_id=200,
                pending_news_id=None,
                source="ap",
                source_trust=0.8,
                source_count=1,
                cluster_variant_count=1,
                priority_score=0.6,
            )
        )
        second_id = _run(
            self.memory.process_cluster_update(
                title="Ukraine ceasefire talks stall over borders",
                summary="Negotiations hit obstacles on territory.",
                tags=["ukraine", "ceasefire"],
                cluster_id=200,
                pending_news_id=None,
                source="bbc",
                source_trust=0.82,
                source_count=2,
                cluster_variant_count=3,
                priority_score=0.65,
            )
        )
        self.assertEqual(first_id, second_id)
        events = self.repo.recent_events(int(first_id), limit=5)
        self.assertGreaterEqual(len(events), 2)


class DigestRankerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = init_database(Path(self._tmp.name) / "test.db")
        self.repo = StoryRepository(self.db_path)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_build_sections(self) -> None:
        self.repo.create_story(
            title="SEC approves spot Bitcoin ETF",
            canonical_summary="Major milestone for crypto markets.",
            importance_score=0.92,
            trend_velocity=0.8,
        )
        ranker = DigestRanker(self.repo)
        sections = ranker.build_sections(limit_per_section=2)
        self.assertTrue(sections)
        self.assertTrue(sections[0].stories)
