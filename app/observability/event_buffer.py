"""Buffered NDJSON event writer (atomic append on flush)."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from ops.pipeline.paths import events_ndjson_path

_buffers: dict[str, "_EventBuffer"] = {}
_lock = threading.Lock()

_FLUSH_INTERVAL_SEC = float(os.getenv("OPS_EVENT_FLUSH_INTERVAL_SEC", "5"))
_FLUSH_MAX_EVENTS = int(os.getenv("OPS_EVENT_FLUSH_MAX_EVENTS", "100"))


class _EventBuffer:
    def __init__(self, runtime_dir: str | None) -> None:
        self._runtime_dir = runtime_dir
        self._buf: list[dict[str, Any]] = []
        self._last_flush = time.monotonic()
        self._io_lock = threading.Lock()

    def append(self, event: dict[str, Any]) -> None:
        with self._io_lock:
            self._buf.append(event)
            if len(self._buf) >= _FLUSH_MAX_EVENTS:
                self._flush_unlocked()
            elif time.monotonic() - self._last_flush >= _FLUSH_INTERVAL_SEC:
                self._flush_unlocked()

    def flush(self, *, force: bool = False) -> None:
        with self._io_lock:
            if force or self._buf:
                self._flush_unlocked()

    def _flush_unlocked(self) -> None:
        if not self._buf:
            return
        path = events_ndjson_path(self._runtime_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".ndjson.tmp")
        lines = "".join(json.dumps(e, ensure_ascii=False, default=str) + "\n" for e in self._buf)
        with tmp.open("a", encoding="utf-8") as fh:
            fh.write(lines)
        with path.open("a", encoding="utf-8") as out:
            out.write(lines)
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        self._buf.clear()
        self._last_flush = time.monotonic()


def get_event_buffer(runtime_dir: str | None) -> _EventBuffer:
    key = str(runtime_dir or os.getenv("RUNTIME_STATE_DIR", "var/runtime"))
    with _lock:
        buf = _buffers.get(key)
        if buf is None:
            buf = _EventBuffer(runtime_dir)
            _buffers[key] = buf
        return buf


def reset_event_buffers_for_tests() -> None:
    with _lock:
        for b in _buffers.values():
            b.flush(force=True)
        _buffers.clear()
