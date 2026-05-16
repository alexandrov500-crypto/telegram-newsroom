from __future__ import annotations

import asyncio

from db.repository import search_drafts_operational
from db.session import close_db, init_db, session_scope
from tests.conftest import minimal_test_settings


def test_search_drafts_operational_no_filters_returns_empty() -> None:
    s = minimal_test_settings()

    async def run() -> list:
        await close_db()
        await init_db(s.database_url, pool_size=s.database_pool_size, max_overflow=s.database_max_overflow)
        try:
            async with session_scope() as session:
                return await search_drafts_operational(session, limit=5)
        finally:
            await close_db()

    assert asyncio.run(run()) == []
