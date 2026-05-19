from __future__ import annotations

import asyncio
from pathlib import Path

from bot.digest.generator import format_digest_body
from bot.processing import entities as ent
from bot.processing.entities import TOPIC_AI, TOPIC_CRYPTO, TOPIC_REGULATION
from bot.storage.db import init_database
from bot.storage.digest_repository import DigestCandidate
from bot.storage.entity_repository import EntityRepository


def test_extract_openai_and_sec_aliases() -> None:
    async def run():
        return await ent.extract_entities(
            "SEC approves Bitcoin ETF framework",
            "The U.S. Securities and Exchange Commission finalized custody rules.",
            ["regulation", "crypto"],
            use_openai=False,
        )

    result = asyncio.run(run())
    names = {entity.display_name for entity in result.entities}
    assert "SEC" in names
    assert TOPIC_REGULATION in result.topics or TOPIC_CRYPTO in result.topics


def test_alias_normalization() -> None:
    left = ent.resolve_entity("openai", ent.ENTITY_COMPANY)
    right = ent.resolve_entity("OpenAI", ent.ENTITY_COMPANY)
    assert left is not None and right is not None
    assert left.normalized_key == right.normalized_key
    assert left.display_name == "OpenAI"


def test_trending_counts_increase(tmp_path: Path) -> None:
    db_path = init_database(tmp_path / "entities_trend.db")
    repo = EntityRepository(db_path)

    async def index_once(title: str, news_id: int) -> None:
        await repo.index_news_item_async(
            title=title,
            summary="Regulators updated ETF guidance for institutional investors.",
            tags=["regulation", "crypto"],
            pending_news_id=news_id,
            cluster_id=None,
            priority_score=0.9,
        )

    asyncio.run(index_once("SEC approves Bitcoin ETF", 1))
    asyncio.run(index_once("SEC expands Bitcoin ETF guidance", 2))

    trending = repo.get_trending_entities(limit=5)
    sec_rows = [row for row in trending if row.entity_name == "SEC"]
    assert sec_rows
    assert sec_rows[0].mention_count >= 1


def test_topic_mapping() -> None:
    async def run():
        return await ent.extract_entities(
            "OpenAI launches GPT update",
            "New model capabilities include reasoning improvements.",
            ["ai", "startups"],
            use_openai=False,
        )

    result = asyncio.run(run())
    assert TOPIC_AI in result.topics or any(
        entity.display_name == TOPIC_AI for entity in result.entities
    )


def test_digest_includes_trending_entities() -> None:
    items = [
        DigestCandidate(
            id=1,
            title="Story",
            summary="Summary text",
            link="https://example.com/1",
            tags=["ai"],
            cluster_id=None,
            priority_score=0.8,
            created_at="2026-05-15T10:00:00+00:00",
        )
    ]
    _, content = format_digest_body(
        digest_type="morning",
        items=items,
        trending_entities=["OpenAI", "SEC", "Bitcoin ETF"],
    )
    assert "🔥 Trending:" in content
    assert "OpenAI" in content
    assert "SEC" in content


def test_malformed_input_fail_open() -> None:
    async def run():
        return await ent.extract_entities("", None, None, use_openai=False)

    result = asyncio.run(run())
    assert isinstance(result.entities, list)
    assert isinstance(result.topics, list)
