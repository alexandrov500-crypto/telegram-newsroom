from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from db import repository as repo
from db.session import close_db, init_db, session_scope
from utils.editorial_insights import collect_editorial_insights
from utils.text_hash import sha256_hex


@pytest.fixture
def sqlite_url(tmp_path) -> str:
    return f"sqlite+aiosqlite:///{tmp_path / 'insights.db'}"


@pytest.fixture(autouse=True)
def db_init(sqlite_url: str):
    asyncio.run(close_db())
    asyncio.run(init_db(sqlite_url))
    yield
    asyncio.run(close_db())


def test_collect_editorial_insights_counts(sqlite_url: str) -> None:
    async def prep() -> None:
        async with session_scope() as session:
            await repo.create_draft(
                session,
                content="technology headline about markets",
                content_hash=sha256_hex("a"),
                sources_payload=[{"channel": "@src1", "message_id": 1}],
            )

    asyncio.run(prep())

    async def run() -> dict:
        async with session_scope() as session:
            return await collect_editorial_insights(session, now=datetime(2026, 5, 12, 15, 0, tzinfo=timezone.utc))

    data = asyncio.run(run())
    assert data["pending_count"] >= 1
    assert "top_sources_today" in data
    assert "trending_topics" in data
