"""In-memory ring buffer of recent structured log lines (no secrets)."""

from __future__ import annotations

import threading
from collections import deque
from typing import Any

_MAX = 400
_lock = threading.Lock()
_lines: deque[str] = deque(maxlen=_MAX)


def reset_log_ring_for_tests() -> None:
    with _lock:
        _lines.clear()


def append_log_line(line: str) -> None:
    s = (line or "").strip()
    if not s:
        return
    with _lock:
        _lines.append(s[:8000])


def recent_log_lines(*, limit: int = 200) -> list[str]:
    n = max(1, min(int(limit), _MAX))
    with _lock:
        return list(_lines)[-n:]
