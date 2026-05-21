"""Bounded in-memory runtime timeline (newest first)."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

_DEFAULT_MAX = 500


@dataclass(slots=True)
class TimelineEntry:
    ts: str
    ts_unix: float
    kind: str
    subsystem: str
    summary: str
    fields: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "ts_unix": self.ts_unix,
            "kind": self.kind,
            "subsystem": self.subsystem,
            "summary": self.summary,
            **self.fields,
        }


_lock = threading.Lock()
_entries: deque[TimelineEntry] = deque(maxlen=_DEFAULT_MAX)
_watchdog_alert_count = 0


def reset_timeline_for_tests() -> None:
    global _watchdog_alert_count
    with _lock:
        _entries.clear()
        _watchdog_alert_count = 0


def _iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _subsystem_from_kind(kind: str) -> str:
    if "." in kind:
        return kind.split(".", 1)[0]
    return "runtime"


def record_timeline(
    kind: str,
    *,
    summary: str = "",
    subsystem: str | None = None,
    **fields: Any,
) -> None:
    ent = TimelineEntry(
        ts=_iso_now(),
        ts_unix=time.time(),
        kind=kind,
        subsystem=subsystem or _subsystem_from_kind(kind),
        summary=(summary or kind)[:240],
        fields={k: v for k, v in fields.items() if k not in {"ts", "kind", "summary"}},
    )
    with _lock:
        _entries.appendleft(ent)


def inc_watchdog_alerts(delta: int = 1) -> None:
    global _watchdog_alert_count
    with _lock:
        _watchdog_alert_count += max(0, delta)


def watchdog_alerts_total() -> int:
    with _lock:
        return _watchdog_alert_count


def timeline_snapshot(*, limit: int = 100) -> list[dict[str, Any]]:
    n = max(1, min(int(limit), _DEFAULT_MAX))
    with _lock:
        return [e.to_dict() for e in list(_entries)[:n]]
