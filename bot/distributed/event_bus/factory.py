from __future__ import annotations

import logging
from typing import Any

from bot.distributed.event_bus.base import DistributedEventBus
from bot.distributed.event_bus.inmemory import InMemoryDistributedBus
from bot.distributed.event_bus.nats_backend import NatsDistributedBus
from bot.distributed.event_bus.redis_backend import RedisDistributedBus
from bot.distributed.redis_client import get_redis_optional

logger = logging.getLogger(__name__)


def create_event_bus(
    *,
    backend: str,
    node_id: str,
    store: Any | None = None,
    redis_url: str | None = None,
    nats_url: str | None = None,
) -> DistributedEventBus:
    name = (backend or "inmemory").strip().lower()
    if name == "redis":
        client = get_redis_optional(redis_url)
        if client is None:
            logger.warning("event=event_bus_fallback backend=inmemory reason=redis_unavailable")
            return InMemoryDistributedBus(store=store)
        return RedisDistributedBus(client, node_id=node_id, store=store)
    if name in ("nats", "kafka"):
        return NatsDistributedBus(nats_url=nats_url, store=store)
    return InMemoryDistributedBus(store=store)
