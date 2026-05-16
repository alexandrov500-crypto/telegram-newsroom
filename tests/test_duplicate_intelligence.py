from __future__ import annotations

import asyncio

from db import repository as repo
from db.session import close_db, init_db, session_scope
from tests.conftest import minimal_test_settings
from utils.text_hash import sha256_hex


def test_duplicate_intel_similar(tmp_path) -> None:
    url = f"sqlite+aiosqlite:///{tmp_path / 'dup.db'}"

    async def body() -> None:
        await close_db()
        await init_db(url)
        try:
            settings = minimal_test_settings(database_url=url)
            async with session_scope() as session:
                await repo.create_draft(
                    session,
                    content="Breaking: foo bar baz qux unique words here",
                    content_hash=sha256_hex("a"),
                    sources_payload=[{"channel": "@a", "message_id": 1}],
                )
                d2 = await repo.create_draft(
                    session,
                    content="Breaking: foo bar baz qux unique words here and more",
                    content_hash=sha256_hex("b"),
                    sources_payload=[{"channel": "@a", "message_id": 2}],
                )
                did2 = int(d2.id)
            async with session_scope() as session:
                intel = await repo.draft_duplicate_intel(
                    session,
                    did2,
                    similarity_threshold=settings.draft_similarity_threshold,
                )
            assert intel["max_similarity_pct"] > 50
            assert intel["severity"] in ("none", "low", "medium", "high")
        finally:
            await close_db()

    asyncio.run(body())
