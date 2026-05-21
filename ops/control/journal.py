"""Append-only operator control action journal."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

_lock = threading.RLock()
_MAX_LINES = int(os.getenv("OPS_ACTION_JOURNAL_MAX_LINES", "5000"))


def action_journal_path(runtime_dir: str) -> Path:
    d = Path(runtime_dir).expanduser().resolve() / "ops"
    d.mkdir(parents=True, exist_ok=True)
    return d / "action_journal.jsonl"


def append_control_action(
    runtime_dir: str,
    *,
    action: str,
    outcome: str,
    correlation_id: str,
    operator: str = "api",
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        from app.runtime_lifecycle import runtime_id

        rid = runtime_id()
    except Exception:
        rid = "unknown"
    entry = {
        "id": f"ops-{uuid.uuid4().hex[:16]}",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "ts_unix": round(time.time(), 3),
        "runtime_id": rid,
        "correlation_id": correlation_id[:64],
        "action": action[:80],
        "outcome": outcome[:80],
        "operator": operator[:40],
        "detail": detail or {},
    }
    path = action_journal_path(runtime_dir)
    line = json.dumps(entry, ensure_ascii=False, default=str) + "\n"
    with _lock:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)
        _trim(path)
    return entry


def query_control_actions(
    runtime_dir: str,
    *,
    limit: int = 100,
    action_prefix: str | None = None,
    since_unix: float | None = None,
) -> list[dict[str, Any]]:
    path = action_journal_path(runtime_dir)
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
                if since_unix and float(row.get("ts_unix") or 0) < since_unix:
                    continue
                if action_prefix and not str(row.get("action") or "").startswith(action_prefix):
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
