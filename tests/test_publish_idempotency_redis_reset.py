from __future__ import annotations

import asyncio
import json
from unittest import mock

from tests.conftest import minimal_test_settings


def test_idempotency_redis_path_survives_memory_reset() -> None:
    from publisher import publish_service as ps

    class _FakeRedis:
        def __init__(self) -> None:
            self.store: dict[str, str] = {}

        async def get(self, key: str):
            return self.store.get(key)

        async def set(self, key: str, value: str, ex: int | None = None):
            self.store[key] = value

    fake = _FakeRedis()

    async def get_redis():
        return fake

    async def body() -> None:
        ps.reset_idempotency_store_for_tests()
        s = minimal_test_settings(redis_enabled=True)
        with mock.patch("utils.redis_client.get_redis", new=get_redis):
            await ps._idem_record_success(s, "restart-key", draft_id=7, message_id=555)
            ps.reset_idempotency_store_for_tests()
            mid = await ps._idem_get_message_id(s, "restart-key")
            assert mid == 555
            raw = await fake.get("newsroom_test:publish_idem:restart-key")
            assert raw is not None
            assert json.loads(raw).get("message_id") == 555

    asyncio.run(body())
