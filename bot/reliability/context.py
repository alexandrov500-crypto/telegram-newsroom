from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import Any, Iterator

import structlog

_correlation_id: str | None = None


def new_correlation_id() -> str:
    return uuid.uuid4().hex[:16]


@contextmanager
def bind_log_context(
    *,
    correlation_id: str | None = None,
    story_id: int | str | None = None,
    cluster_id: int | str | None = None,
    subsystem: str | None = None,
    publish_mode: str | None = None,
    **extra: Any,
) -> Iterator[None]:
    """Bind structured logging fields for the current async context."""
    cid = correlation_id or new_correlation_id()
    fields: dict[str, Any] = {"correlation_id": cid}
    if story_id is not None:
        fields["story_id"] = story_id
    if cluster_id is not None:
        fields["cluster_id"] = cluster_id
    if subsystem is not None:
        fields["subsystem"] = subsystem
    if publish_mode is not None:
        fields["publish_mode"] = publish_mode
    fields.update({k: v for k, v in extra.items() if v is not None})
    structlog.contextvars.bind_contextvars(**fields)
    try:
        yield
    finally:
        structlog.contextvars.unbind_contextvars(*fields.keys())


def log_event(
    logger: Any,
    event: str,
    *,
    latency_ms: float | None = None,
    retry_count: int | None = None,
    token_cost: float | None = None,
    level: str = "info",
    **fields: Any,
) -> None:
    payload = {"event": event, **fields}
    if latency_ms is not None:
        payload["latency_ms"] = round(latency_ms, 2)
    if retry_count is not None:
        payload["retry_count"] = retry_count
    if token_cost is not None:
        payload["token_cost"] = round(token_cost, 6)
    getattr(logger, level)(**payload)
