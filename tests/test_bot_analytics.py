from __future__ import annotations

from pathlib import Path

from bot.digest.generator import format_digest_body
from bot.processing.adaptive import pick_adaptive_hook, priority_boost_from_virality
from bot.processing.engagement import calculate_engagement_score
from bot.processing.headlines import generate_hook_line
from bot.storage.analytics_repository import AnalyticsRepository
from bot.storage.db import init_database


def test_engagement_score_normalized() -> None:
    low = calculate_engagement_score(views=10, forwards=0, reactions=0)
    high = calculate_engagement_score(
        views=20_000,
        forwards=500,
        reactions=120,
        source_trust=0.9,
        topic_virality=0.8,
    )
    assert 0.0 <= low <= 1.0
    assert 0.0 <= high <= 1.0
    assert high > low


def test_analytics_persist_and_top_posts(tmp_path: Path) -> None:
    db_path = init_database(tmp_path / "analytics.db")
    repo = AnalyticsRepository(db_path)

    post_id = repo.record_published_post(
        telegram_message_id=101,
        pending_news_id=1,
        cluster_id=None,
        headline="SEC approves Bitcoin ETF",
        hook_line="📈 Markets react",
        entities=["SEC", "Bitcoin ETF"],
        topics=["crypto", "regulation"],
        priority_score=0.9,
        source_trust=0.8,
    )
    assert post_id is not None

    score = repo.record_analytics_snapshot(
        post_id,
        views=5000,
        forwards=120,
        reactions=40,
        source_trust=0.8,
        topic_virality=0.7,
    )
    assert score is not None
    repo.learn_from_post(
        repo.list_posts_for_collection(limit=1)[0],
        score,
    )

    top = repo.get_top_posts(limit=1)
    assert len(top) == 1
    assert top[0].engagement_score > 0
    assert top[0].views == 5000


def test_top_topics_and_headline_patterns(tmp_path: Path) -> None:
    db_path = init_database(tmp_path / "analytics_topics.db")
    repo = AnalyticsRepository(db_path)
    post_id = repo.record_published_post(
        telegram_message_id=202,
        pending_news_id=2,
        cluster_id=None,
        headline="OpenAI launches new model",
        hook_line="🔥 Major AI update",
        entities=["OpenAI"],
        topics=["ai"],
        priority_score=0.85,
        source_trust=0.7,
    )
    assert post_id is not None
    score = repo.record_analytics_snapshot(
        post_id,
        views=8000,
        forwards=200,
        reactions=50,
        source_trust=0.7,
        topic_virality=0.75,
    )
    assert score is not None
    repo.learn_from_post(repo.list_posts_for_collection(limit=1)[0], score)

    topics = repo.get_top_topics(limit=3)
    assert topics
    assert topics[0].signal_key == "en:ai"

    patterns = repo.get_best_headline_patterns(limit=3)
    assert patterns


def test_adaptive_feedback_hook_and_priority() -> None:
    hook = generate_hook_line(
        title="OpenAI update",
        summary="New capabilities announced.",
        entities=["OpenAI"],
        hook_signals=[("🔥", 0.82)],
    )
    assert hook is not None
    adaptive_hook = pick_adaptive_hook("⚠️ Regulatory update", [("🔥", 0.82)])
    assert adaptive_hook == "🔥 Major AI update"
    assert priority_boost_from_virality(0.8) > 0
    assert priority_boost_from_virality(0.4) == 0


def test_digest_intelligence_block() -> None:
    _, content = format_digest_body(
        digest_type="morning",
        items=[],
        digest_intelligence={
            "most_engaged_story": "SEC approves Bitcoin ETF",
            "trending_topic": "crypto",
            "top_entity": "SEC",
        },
    )
    assert "🔥 Most engaged story:" in content
    assert "📈 Trending topic:" in content
    assert "🏆 Top entity:" in content
    assert "SEC approves Bitcoin ETF" in content
