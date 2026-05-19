from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from bot.editorial.agents import (
    StoryAgentContext,
    evaluate_story_risk,
    should_auto_approve,
    should_trigger_breaking_alert,
)
from bot.editorial.agent_service import EditorialAgentService
from bot.runtime.state import runtime_state
from bot.storage.agent_repository import (
    ACTION_AUTO_APPROVED,
    ACTION_BREAKING_ALERT,
    AgentRepository,
)
from bot.storage.db import init_database
from bot.processing.entities import ENTITY_COMPANY, ExtractedEntity
from bot.storage.editorial_repository import EditorialRepository
from bot.storage.entity_repository import EntityRepository
from bot.storage.source_repository import SourceRepository


def _low_risk_ctx(**overrides: object) -> StoryAgentContext:
    base = dict(
        pending_news_id=1,
        title="OpenAI releases API update for developers",
        summary="Official blog post confirms rollout to enterprise customers.",
        tags=["ai", "tech"],
        source="trusted-wire",
        source_count=3,
        priority_score=0.88,
        source_trust=0.82,
        source_approval_ratio=0.75,
        entity_names=["OpenAI"],
        cluster_variant_count=3,
        topic_virality=0.6,
    )
    base.update(overrides)
    return StoryAgentContext(**base)


def _high_risk_ctx(**overrides: object) -> StoryAgentContext:
    base = dict(
        pending_news_id=2,
        title="Unverified insider tip: guaranteed returns on penny stock",
        summary="Rumor claims massive pump incoming without sources.",
        tags=["rumor", "finance"],
        source="sketch-feed",
        source_count=1,
        priority_score=0.4,
        source_trust=0.3,
        source_approval_ratio=0.2,
        entity_names=[],
        cluster_variant_count=1,
        topic_virality=0.4,
    )
    base.update(overrides)
    return StoryAgentContext(**base)


def test_low_risk_story_can_auto_approve() -> None:
    ctx = _low_risk_ctx()
    assessment = evaluate_story_risk(ctx)
    assert assessment.requires_human_review is False
    assert assessment.risk_score <= 0.35
    assert should_auto_approve(ctx, assessment, auto_approval_enabled=True)


def test_high_risk_story_requires_human_review() -> None:
    ctx = _high_risk_ctx()
    assessment = evaluate_story_risk(ctx)
    assert assessment.requires_human_review is True
    assert assessment.risk_score > 0.35
    assert not should_auto_approve(ctx, assessment, auto_approval_enabled=True)


def test_safeguards_block_political_misinformation() -> None:
    ctx = _low_risk_ctx(
        title="Election ballot fraud campaign deep state propaganda",
        source_count=1,
        entity_names=[],
    )
    assessment = evaluate_story_risk(ctx)
    assert "political_misinformation" in assessment.blocked_categories
    assert not should_auto_approve(ctx, assessment, auto_approval_enabled=True)


def test_safeguards_block_medical_misinformation() -> None:
    ctx = _low_risk_ctx(
        title="Miracle treatment cure for all diseases",
        summary="Anti-vax vaccine hoax spreads online.",
    )
    assessment = evaluate_story_risk(ctx)
    assert "medical_misinformation" in assessment.blocked_categories
    assert not should_auto_approve(ctx, assessment, auto_approval_enabled=True)


def test_breaking_alert_on_high_priority_convergence() -> None:
    ctx = _low_risk_ctx(priority_score=0.9, source_count=3)
    assessment = evaluate_story_risk(ctx)
    assert should_trigger_breaking_alert(ctx, assessment)


def test_breaking_alert_blocked_when_guardrails_fire() -> None:
    ctx = _high_risk_ctx(
        title="Breaking: unverified insider tip guaranteed returns",
        priority_score=0.95,
    )
    assessment = evaluate_story_risk(ctx)
    assert not should_trigger_breaking_alert(ctx, assessment)


def test_risk_assessment_audit_trail(tmp_path: Path) -> None:
    db_path = init_database(tmp_path / "agents.db")
    agent_repo = AgentRepository(db_path)
    ctx = _low_risk_ctx()
    assessment = evaluate_story_risk(ctx)
    row_id = agent_repo.save_risk_assessment(42, assessment)
    assert row_id is not None
    record = agent_repo.get_latest_risk_assessment(42)
    assert record is not None
    assert record.risk_score == assessment.risk_score
    assert record.confidence_score == assessment.publish_confidence


def test_agent_action_reversal_is_audited(tmp_path: Path) -> None:
    db_path = init_database(tmp_path / "agents_reverse.db")
    agent_repo = AgentRepository(db_path)
    action_id = agent_repo.record_action(
        pending_news_id=7,
        action_type=ACTION_AUTO_APPROVED,
        decision={"risk_score": 0.2},
        reversible=True,
    )
    assert action_id is not None
    assert agent_repo.reverse_latest_auto_approval(7)
    actions = agent_repo.recent_actions(limit=5)
    auto_row = next(a for a in actions if a.action_type == ACTION_AUTO_APPROVED)
    assert auto_row.reversed_at is not None


def test_agent_service_auto_publishes_low_risk(tmp_path: Path) -> None:
    async def run() -> None:
        db_path = init_database(tmp_path / "agent_service.db")
        editorial = EditorialRepository(db_path)
        agent_repo = AgentRepository(db_path)
        news_id = editorial.enqueue_news(
            title="OpenAI ships enterprise API update",
            summary="Three wire services confirm rollout.",
            link="https://example.com/openai-api",
            tags=["ai"],
            source="trusted-wire",
            priority_score=0.9,
            source_count=3,
        )
        assert news_id is not None

        entities = EntityRepository(db_path)
        sources = SourceRepository(db_path)
        for _ in range(6):
            sources.record_approval("trusted-wire")
        entity_id = entities.upsert_entity(
            ExtractedEntity(
                display_name="OpenAI",
                entity_type=ENTITY_COMPANY,
                normalized_key="openai",
            )
        )
        assert entity_id is not None
        entities.link_news_entity(entity_id=entity_id, pending_news_id=news_id)

        publisher = MagicMock()
        publisher.channel_configured = True
        publish_result = MagicMock(
            success=True, message_id=999, channel_id="-1001", duration_ms=10
        )
        publisher.publish_news = AsyncMock(return_value=publish_result)

        service = EditorialAgentService(
            agent_repo,
            editorial,
            publisher,
            sources=sources,
            entities=entities,
        )
        runtime_state.auto_approval_enabled = True
        try:
            result = await service.process_new_pending(news_id)
        finally:
            runtime_state.auto_approval_enabled = False

        assert result.auto_approved is True
        assert result.published is True
        item = editorial.get_by_id(news_id)
        assert item is not None
        assert item.status == "published"
        actions = agent_repo.recent_actions(limit=10)
        assert any(a.action_type == ACTION_AUTO_APPROVED for a in actions)

    asyncio.run(run())


def test_agent_service_skips_high_risk(tmp_path: Path) -> None:
    async def run() -> None:
        db_path = init_database(tmp_path / "agent_service_high.db")
        editorial = EditorialRepository(db_path)
        agent_repo = AgentRepository(db_path)
        news_id = editorial.enqueue_news(
            title="Unverified insider tip: guaranteed returns",
            summary="Rumor without corroboration.",
            link="https://example.com/rumor-stock",
            tags=["rumor", "finance"],
            source="sketch-feed",
            priority_score=0.35,
            source_count=1,
        )
        assert news_id is not None

        publisher = MagicMock()
        publisher.channel_configured = True
        publisher.publish_news = AsyncMock()

        service = EditorialAgentService(agent_repo, editorial, publisher)
        runtime_state.auto_approval_enabled = True
        try:
            result = await service.process_new_pending(news_id)
        finally:
            runtime_state.auto_approval_enabled = False

        assert result.auto_approved is False
        assert result.published is False
        publisher.publish_news.assert_not_called()
        assessment = agent_repo.get_latest_risk_assessment(news_id)
        assert assessment is not None
        assert assessment.requires_human_review

    asyncio.run(run())


def test_agent_service_records_breaking_without_auto_publish(tmp_path: Path) -> None:
    async def run() -> None:
        db_path = init_database(tmp_path / "agent_breaking.db")
        editorial = EditorialRepository(db_path)
        agent_repo = AgentRepository(db_path)
        news_id = editorial.enqueue_news(
            title="Ransomware cyberattack hits major cloud provider",
            summary="Three trusted wires confirm ongoing breach response.",
            link="https://example.com/cyber-breaking",
            tags=["security"],
            source="trusted-wire",
            priority_score=0.88,
            source_count=3,
        )
        assert news_id is not None

        entities = EntityRepository(db_path)
        entity_id = entities.upsert_entity(
            ExtractedEntity(
                display_name="Microsoft",
                entity_type=ENTITY_COMPANY,
                normalized_key="microsoft",
            )
        )
        assert entity_id is not None
        entities.link_news_entity(entity_id=entity_id, pending_news_id=news_id)

        sources = SourceRepository(db_path)
        for _ in range(6):
            sources.record_approval("trusted-wire")

        publisher = MagicMock()
        publisher.channel_configured = True
        publisher.publish_news = AsyncMock()

        service = EditorialAgentService(
            agent_repo,
            editorial,
            publisher,
            sources=sources,
            entities=entities,
        )
        runtime_state.auto_approval_enabled = False
        result = await service.process_new_pending(news_id)

        assert result.breaking_alert is True
        assert result.auto_approved is False
        assert result.published is False
        publisher.publish_news.assert_not_called()
        actions = {a.action_type for a in agent_repo.recent_actions(limit=20)}
        assert ACTION_BREAKING_ALERT in actions

    asyncio.run(run())
