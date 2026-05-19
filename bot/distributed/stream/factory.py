from __future__ import annotations

import logging
import os
from typing import Any

from bot.distributed.event_bus.base import DistributedEventBus
from bot.distributed.event_bus.factory import create_event_bus as create_legacy_bus
from bot.distributed.event_bus.inmemory import InMemoryDistributedBus
from bot.distributed.redis_client import get_redis_optional
from bot.distributed.stream.base import StreamEventBus
from bot.distributed.stream.inmemory_stream import InMemoryStreamBus
from bot.distributed.stream.jetstream_stub import JetStreamBus
from bot.distributed.stream.redis_streams import RedisStreamsBus

logger = logging.getLogger(__name__)


def _stream_backend_name() -> str:
    return (
        os.getenv("STREAM_BACKEND", "").strip().lower()
        or os.getenv("EVENT_BUS_BACKEND", "inmemory").strip().lower()
    )


def create_stream_bus(
    *,
    node_id: str,
    store: Any | None = None,
    sourced_store: Any | None = None,
    redis_url: str | None = None,
    nats_url: str | None = None,
) -> StreamEventBus | DistributedEventBus:
    """
    Create durable stream bus when STREAM_BACKEND / EVENT_BUS_BACKEND requests it.
    Falls back to legacy pub/sub or in-memory stream.
    """
    backend = _stream_backend_name()
    if backend in ("redis_streams", "streams"):
        client = get_redis_optional(redis_url)
        if client is None:
            logger.warning("event=stream_fallback backend=inmemory_stream")
            return InMemoryStreamBus(store=store, sourced_store=sourced_store)
        return RedisStreamsBus(
            client,
            node_id=node_id,
            sourced_store=sourced_store,
        )
    if backend in ("jetstream", "nats_jetstream"):
        return JetStreamBus(nats_url=nats_url, store=store, sourced_store=sourced_store)
    if backend == "inmemory_stream":
        return InMemoryStreamBus(store=store, sourced_store=sourced_store)
    if backend == "redis":
        return create_legacy_bus(
            backend="redis",
            node_id=node_id,
            store=store,
            redis_url=redis_url,
        )
    if backend in ("nats", "kafka"):
        return create_legacy_bus(
            backend=backend,
            node_id=node_id,
            store=store,
            nats_url=nats_url,
        )
    return InMemoryStreamBus(store=store, sourced_store=sourced_store)


def wrap_with_envelope_publish(
    bus: DistributedEventBus,
    *,
    node_id: str,
    region: str,
    sourced_store: Any | None = None,
) -> DistributedEventBus:
    """Migration layer: legacy publish() writes sourced log + envelope when possible."""
    if isinstance(bus, StreamEventBus):
        return bus
    if isinstance(bus, InMemoryDistributedBus) and sourced_store is not None:
        return InMemoryStreamBus(store=bus._inner._store, sourced_store=sourced_store)  # noqa: SLF001
    return bus
