from __future__ import annotations

import asyncio

from tests.conftest import minimal_test_settings


def test_idempotency_memory_store_roundtrip() -> None:
    from publisher import publish_service as ps

    async def body() -> None:
        ps.reset_idempotency_store_for_tests()
        s = minimal_test_settings()
        await ps._idem_record_success(s, "idem-key-1", draft_id=3, message_id=999)
        mid = await ps._idem_get_message_id(s, "idem-key-1")
        assert mid == 999

    asyncio.run(body())


def test_idempotency_memory_concurrent_writes_stable() -> None:
    from publisher import publish_service as ps

    async def body() -> None:
        ps.reset_idempotency_store_for_tests()
        s = minimal_test_settings()

        async def rec(mid: int) -> None:
            await ps._idem_record_success(s, "shared", draft_id=1, message_id=mid)

        await asyncio.gather(rec(10), rec(11), rec(12))
        mid = await ps._idem_get_message_id(s, "shared")
        assert mid in (10, 11, 12)

    asyncio.run(body())
