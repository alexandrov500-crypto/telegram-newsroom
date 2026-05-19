from __future__ import annotations

from pathlib import Path

import pytest

from bot.events.envelope import EventEnvelope, CURRENT_ENVELOPE_VERSION
from bot.events.validation import EventValidationError, validate_envelope, is_poison_message
from bot.publishing.idempotency import PublishIdempotencyStore
from bot.storage.db import init_database
from bot.storage.sourced_event_store import SourcedEventStore
from bot.distributed.stream.inmemory_stream import InMemoryStreamBus
from bot.workflows.checkpoint_store import WorkflowCheckpointStore
from bot.workflows.orchestrator import WorkflowOrchestrator
from bot.workflows.types import WorkflowType


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return init_database(tmp_path / "sourced.db")


def test_envelope_roundtrip() -> None:
    env = EventEnvelope(
        event_type="StoryIngested",
        payload={"story_id": 1},
        node_id="n1",
        region="eu",
        correlation_id="corr-1",
    )
    validate_envelope(env)
    restored = EventEnvelope.from_dict(env.to_dict(sign=False), verify_signature=False)
    assert restored.event_type == "StoryIngested"
    assert restored.event_version == CURRENT_ENVELOPE_VERSION


def test_poison_detection() -> None:
    env = EventEnvelope(event_type="SignalDetected", payload={}, retry_count=5)
    assert is_poison_message(env)


def test_sourced_event_append_and_replay(db_path: Path) -> None:
    store = SourcedEventStore(db_path)
    env = EventEnvelope(event_type="DigestStarted", payload={"digest_type": "hourly"}, node_id="d1")
    seq = store.append(env)
    assert seq >= 1
    replayed = store.replay_range(from_sequence=1, limit=10)
    assert len(replayed) == 1
    store.mark_processed(env.event_id)
    assert store.count_by_status("processed") == 1


def test_publish_idempotency(db_path: Path) -> None:
    store = PublishIdempotencyStore(db_path)
    key = store.build_key(pending_news_id=99, channel_id=-1001, language="en", content_hash="link")
    assert store.try_begin(key, pending_news_id=99, digest_id=None, channel_id=-1001, language="en", node_id="n1") is None
    store.complete(key, telegram_message_id=555)
    dup = store.try_begin(key, pending_news_id=99, digest_id=None, channel_id=-1001, language="en", node_id="n2")
    assert dup is not None
    assert dup.telegram_message_id == 555


def test_inmemory_stream_publish(db_path: Path) -> None:
    import asyncio

    async def _run() -> None:
        sourced = SourcedEventStore(db_path)
        bus = InMemoryStreamBus(sourced_store=sourced)
        bus.start()
        seen: list[str] = []

        async def on_env(env: EventEnvelope) -> None:
            seen.append(env.event_type)

        bus.subscribe_envelope("StoryUpdated", on_env)
        env = EventEnvelope(event_type="StoryUpdated", payload={"id": 1}, node_id="t")
        await bus.publish_envelope(env)
        await asyncio.sleep(0.05)
        await bus.stop()
        assert "StoryUpdated" in seen

    asyncio.run(_run())


def test_workflow_checkpoints(db_path: Path) -> None:
    import asyncio

    store = WorkflowCheckpointStore(db_path)

    async def step_collect(run, state):
        return {**state, "items": [1, 2]}

    async def step_publish(run, state):
        return {**state, "published": True}

    orch = WorkflowOrchestrator(store, node_id="wf-node")

    async def _run():
        return await orch.run(
            WorkflowType.DIGEST,
            correlation_id="digest-hourly-1",
            steps=[("collect", step_collect), ("publish", step_publish)],
            initial={},
        )

    result = asyncio.run(_run())
    assert result.get("published") is True
    assert result.get("items") == [1, 2]
