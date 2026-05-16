from __future__ import annotations

import asyncio

from tests.conftest import minimal_test_settings


def test_publish_draft_lock_local_acquires() -> None:
    from publisher.publish_lock import publish_draft_lock

    async def body() -> None:
        s = minimal_test_settings()
        async with publish_draft_lock(s, 4242) as ok:
            assert ok is True

    asyncio.run(body())
