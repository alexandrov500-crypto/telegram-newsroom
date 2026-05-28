"""Structured ops events (feeds event buffer)."""

from __future__ import annotations

import time
from typing import Any


def _runtime_id() -> str:
    try:
        from app.runtime_lifecycle import runtime_id

        return runtime_id()
    except Exception:
        return "unknown"


def emit_ops_event(
    event: str,
    *,
    runtime_dir: str | None = None,
    news_id: str = "",
    state: str = "",
    decision_reason: str = "",
    **fields: Any,
) -> None:
    payload: dict[str, Any] = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "ts_unix": round(time.time(), 3),
        "runtime_id": _runtime_id(),
        "event": event,
        "news_id": news_id,
        "state": state,
        "decision_reason": decision_reason,
        **fields,
    }
    try:
        from app.observability.event_buffer import get_event_buffer

        get_event_buffer(runtime_dir).append(payload)
    except Exception:
        pass
