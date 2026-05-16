from __future__ import annotations

import asyncio

import pytest

from db import repository as repo
from db.session import close_db, init_db, session_scope
from utils.text_hash import sha256_hex


@pytest.fixture
def sqlite_url(tmp_path) -> str:
    return f"sqlite+aiosqlite:///{tmp_path / 'queue_sort.db'}"


@pytest.fixture(autouse=True)
def db_init(sqlite_url: str):
    asyncio.run(close_db())
    asyncio.run(init_db(sqlite_url))
    yield
    asyncio.run(close_db())


def test_queue_priority_sorting(sqlite_url: str) -> None:
    async def prep() -> None:
        async with session_scope() as session:
            d1 = await repo.create_draft(
                session,
                content="low",
                content_hash=sha256_hex("low"),
                sources_payload=[{"channel": "@a", "message_id": 1}],
            )
            d2 = await repo.create_draft(
                session,
                content="high",
                content_hash=sha256_hex("high"),
                sources_payload=[{"channel": "@b", "message_id": 2}],
            )
            await repo.merge_draft_extras(
                session,
                int(d1.id),
                {"priority": {"numeric_priority_score": 0.2, "priority_level": "LOW"}},
            )
            await repo.merge_draft_extras(
                session,
                int(d2.id),
                {"priority": {"numeric_priority_score": 0.95, "priority_level": "HIGH"}},
            )

    asyncio.run(prep())

    async def run() -> list[int]:
        async with session_scope() as session:
            rows = await repo.list_pending_drafts_for_queue(session, limit=10, offset=0, mode="priority")
            return [int(r.id) for r in rows]

    ids = asyncio.run(run())
    assert ids[0] > ids[1]


def test_queue_breaking_first(sqlite_url: str) -> None:
    async def prep() -> None:
        async with session_scope() as session:
            d1 = await repo.create_draft(
                session,
                content="a",
                content_hash=sha256_hex("a2"),
                sources_payload=[{"channel": "@a", "message_id": 1}],
            )
            d2 = await repo.create_draft(
                session,
                content="b",
                content_hash=sha256_hex("b2"),
                sources_payload=[{"channel": "@b", "message_id": 2}],
            )
            await repo.merge_draft_extras(session, int(d1.id), {"breaking": {"is_breaking": False, "breaking_score": 0.1}})
            await repo.merge_draft_extras(session, int(d2.id), {"breaking": {"is_breaking": True, "breaking_score": 0.9}})

    asyncio.run(prep())

    async def run() -> list[int]:
        async with session_scope() as session:
            rows = await repo.list_pending_drafts_for_queue(session, limit=10, offset=0, mode="breaking")
            return [int(r.id) for r in rows]

    ids = asyncio.run(run())
    assert ids[0] > ids[1]
