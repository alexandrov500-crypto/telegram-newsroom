from __future__ import annotations

import logging
from typing import Any

from bot.distributed.stream.inmemory_stream import InMemoryStreamBus

logger = logging.getLogger(__name__)


class JetStreamBus(InMemoryStreamBus):
    """NATS JetStream placeholder — falls back to in-memory stream semantics."""

    backend_name = "jetstream"

    def __init__(
        self,
        *,
        nats_url: str | None = None,
        store: Any | None = None,
        sourced_store: Any | None = None,
    ) -> None:
        if nats_url:
            logger.info("event=jetstream_stub_active url=%s", nats_url)
        super().__init__(store=store, sourced_store=sourced_store)
