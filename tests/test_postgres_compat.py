from __future__ import annotations

import asyncio
import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("NEWSROOM_TEST_POSTGRES_URL"),
    reason="NEWSROOM_TEST_POSTGRES_URL not set (optional integration)",
)


def test_postgres_async_engine_select_one() -> None:
    from sqlalchemy import text

    from db.session import close_db, get_engine, init_db
    from utils.database_url import normalize_async_database_url

    url = normalize_async_database_url(os.environ["NEWSROOM_TEST_POSTGRES_URL"])

    async def body() -> None:
        await init_db(url, pool_size=2, max_overflow=2)
        try:
            eng = get_engine()
            async with eng.connect() as conn:
                await conn.execute(text("SELECT 1"))
        finally:
            await close_db()

    asyncio.run(body())
