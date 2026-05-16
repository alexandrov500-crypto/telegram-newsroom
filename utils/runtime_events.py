from __future__ import annotations

import itertools
import json
import threading
import time
from collections import deque
from typing import Any

_lock = threading.RLock()
_buffer: deque[dict[str, Any]] = deque(maxlen=256)
_seq = itertools.count(1)


def configure_runtime_event_buffer(maxlen: int = 256) -> None:
    global _buffer
    with _lock:
        n = max(1, min(int(maxlen), 4096))
        _buffer = deque(list(_buffer)[-n:], maxlen=n)


def _json_safe(v: Any) -> Any:
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    if isinstance(v, dict):
        return {str(k): _json_safe(val) for k, val in list(v.items())[:48]}
    if isinstance(v, (list, tuple)):
        return [_json_safe(x) for x in v[:48]]
    return str(v)


def append_runtime_event(
    kind: str,
    *,
    message: str = "",
    **fields: Any,
) -> dict[str, Any]:
    """Append a JSON-serializable event (bounded ring, FIFO)."""
    ev: dict[str, Any] = {
        "seq": int(next(_seq)),
        "ts_monotonic": round(time.monotonic(), 6),
        "kind": str(kind),
        "message": str(message),
    }
    for k, v in fields.items():
        if str(k) in ev:
            continue
        ev[str(k)] = _json_safe(v)
    try:
        from utils.operational_context import get_operational_log_fields

        for ok, ov in get_operational_log_fields().items():
            if ok not in ev:
                ev[ok] = _json_safe(ov)
    except Exception:
        pass
    with _lock:
        _buffer.append(ev)
    return dict(ev)


def get_recent_runtime_events(limit: int = 64) -> list[dict[str, Any]]:
    n = max(0, min(int(limit), len(_buffer)))
    with _lock:
        if n == 0:
            return []
        return [dict(x) for x in list(_buffer)[-n:]]


def clear_runtime_events() -> None:
    with _lock:
        _buffer.clear()


def reset_runtime_events_for_tests() -> None:
    """Clear buffer and reset seq (pytest)."""
    global _seq
    with _lock:
        _buffer.clear()
        _seq = itertools.count(1)
