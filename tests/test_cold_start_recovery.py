from __future__ import annotations

import asyncio

from db.session import close_db, init_db
from tests.helpers.runtime_factory import build_ephemeral_settings
from tests.conftest import minimal_test_settings
from utils.runtime_health import gather_runtime_health


def test_cold_start_runtime_health_ok(tmp_path) -> None:
    s = build_ephemeral_settings(minimal_test_settings(), tmp_path)

    async def run() -> bool:
        await close_db()
        await init_db(s.database_url, pool_size=s.database_pool_size, max_overflow=s.database_max_overflow)
        try:
            h = await gather_runtime_health(s, include_openai=False)
            return bool(h.get("ok"))
        finally:
            await close_db()

    assert asyncio.run(run()) is True
