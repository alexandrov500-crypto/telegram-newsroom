from __future__ import annotations

import asyncio

from dashboard import build_operational_dashboard_bundle
from db.session import close_db, init_db
from tests.conftest import minimal_test_settings


def test_operational_dashboard_bundle_keys() -> None:
    s = minimal_test_settings()

    async def run() -> dict:
        await close_db()
        await init_db(s.database_url, pool_size=s.database_pool_size, max_overflow=s.database_max_overflow)
        try:
            b = await build_operational_dashboard_bundle(s, include_openai=False)
            return b.to_dict()
        finally:
            await close_db()

    d = asyncio.run(run())
    for k in ("runtime", "editorial", "warnings", "timeline_tail", "editorial_operational"):
        assert k in d
