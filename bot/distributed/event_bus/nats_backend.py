from __future__ import annotations

import logging

from bot.distributed.event_bus.inmemory import InMemoryDistributedBus

logger = logging.getLogger(__name__)


class NatsDistributedBus(InMemoryDistributedBus):
    """
    NATS/Kafka-ready stub: falls back to in-memory with warning until broker wired.
    Interface preserved for future jetstream / kafka adapter.
    """

    backend_name = "nats"

    def __init__(self, *, nats_url: str | None = None, **kwargs: object) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        if nats_url:
            logger.warning(
                "event=nats_bus_stub_active url=%s reason=broker_not_configured",
                nats_url,
            )
