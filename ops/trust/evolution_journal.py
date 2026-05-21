"""Append-only evolution history (deployments, policy, modes)."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from ops.trust.paths import evolution_journal_path

_lock = threading.RLock()
_MAX_LINES = int(os.getenv("EVOLUTION_JOURNAL_MAX_LINES", "3000"))


def append_evolution_event(
    runtime_dir: str,
    *,
    event_type: str,
    summary: str,
    detail: dict[str, Any] | None = None,
    correlation_id: str = "",
) -> dict[str, Any]:
    try:
        from app.runtime_lifecycle import runtime_id

        rid = runtime_id()
    except Exception:
        rid = "unknown"
    entry = {
        "id": f"evo-{uuid.uuid4().hex[:14]}",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "ts_unix": round(time.time(), 3),
        "runtime_id": rid,
        "event_type": event_type[:60],
        "summary": summary[:240],
        "correlation_id": correlation_id[:64],
        "detail": detail or {},
    }
    path = evolution_journal_path(runtime_dir)
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        _trim(path)
    return entry


def query_evolution_history(
    runtime_dir: str,
    *,
    limit: int = 100,
    event_type: str | None = None,
) -> list[dict[str, Any]]:
    path = evolution_journal_path(runtime_dir)
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(row, dict):
                    continue
                if event_type and row.get("event_type") != event_type:
                    continue
                rows.append(row)
    except OSError:
        return []
    return list(reversed(rows[-limit:]))


def _trim(path: Path) -> None:
    try:
        with path.open(encoding="utf-8") as fh:
            lines = fh.readlines()
        if len(lines) <= _MAX_LINES:
            return
        path.write_text("".join(lines[-_MAX_LINES:]), encoding="utf-8")
    except OSError:
        pass
