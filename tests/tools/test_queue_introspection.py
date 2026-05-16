"""Read-only queue introspection tests."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from tests.conftest import minimal_test_settings
from utils.queue_introspection import collect_queue_introspection
from worker.job_queue import JobKind


def test_redis_queue_counts_read_only(monkeypatch: pytest.MonkeyPatch) -> None:
    r = MagicMock()
    r.llen = AsyncMock(return_value=2)
    r.lindex = AsyncMock(
        return_value=json.dumps(
            {
                "kind": "publisher",
                "payload": {"_enqueue_wall_ts": 1_000_000_000.0},
                "retry": {"attempt": 0},
            }
        )
    )

    async def _scan(*_a: object, **_k: object):
        yield b"newsroom:publish_lock:42"

    r.scan_iter = _scan
    r.ttl = AsyncMock(return_value=120)

    async def get_redis() -> MagicMock:
        return r

    monkeypatch.setattr("utils.redis_client.get_redis", get_redis)
    s = minimal_test_settings(redis_enabled=True)

    async def run() -> dict:
        return await collect_queue_introspection(s)

    report = asyncio.run(run())
    assert report["read_only"] is True
    assert report["no_redis_mutations"] is True
    assert report["queues"]["publisher"]["pending_count"] == 2
    assert report["queues"]["publisher"]["dlq_count"] == 2
    r.lpop.assert_not_called()
    r.brpop.assert_not_called()


def test_memory_mode_without_queue_init(monkeypatch: pytest.MonkeyPatch) -> None:
    async def get_redis() -> None:
        return None

    monkeypatch.setattr("utils.redis_client.get_redis", get_redis)
    s = minimal_test_settings(redis_enabled=False)
    report = asyncio.run(collect_queue_introspection(s))
    assert report["transport_mode"] == "memory"
    assert report["queues"][JobKind.INGEST.value]["note"]
