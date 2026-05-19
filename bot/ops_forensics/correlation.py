from __future__ import annotations

import uuid
from contextvars import ContextVar

_correlation_id: ContextVar[str | None] = ContextVar("ops_correlation_id", default=None)
_publish_id: ContextVar[str | None] = ContextVar("ops_publish_id", default=None)


def new_correlation_id(*, prefix: str = "op") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def get_correlation_id() -> str | None:
    return _correlation_id.get()


def set_correlation_id(correlation_id: str | None) -> None:
    _correlation_id.set(correlation_id)


def get_publish_id() -> str | None:
    return _publish_id.get()


def set_publish_id(publish_id: str | int | None) -> None:
    if publish_id is None:
        _publish_id.set(None)
    else:
        _publish_id.set(str(publish_id))


def ensure_correlation_id(*, prefix: str = "pub") -> str:
    cid = get_correlation_id()
    if not cid:
        cid = new_correlation_id(prefix=prefix)
        set_correlation_id(cid)
    return cid


def bind_publish_context(
    *,
    pending_news_id: int | None,
    correlation_id: str | None = None,
) -> str:
    if pending_news_id is not None:
        set_publish_id(pending_news_id)
    return ensure_correlation_id(prefix="pub") if correlation_id is None else correlation_id
