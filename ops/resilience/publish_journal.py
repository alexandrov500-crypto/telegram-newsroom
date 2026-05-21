"""Crash-safe publish journal (append-only JSONL, idempotent recovery)."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Literal

from ops.resilience.paths import publish_journal_path

_lock = threading.RLock()
_MAX_LINES = int(os.getenv("PUBLISH_JOURNAL_MAX_LINES", "10000"))
_MAX_BYTES = int(os.getenv("PUBLISH_JOURNAL_MAX_BYTES", str(12_000_000)))

PublishState = Literal[
    "initiated",
    "lock_acquired",
    "approved",
    "sending",
    "sent",
    "finalized",
    "failed",
    "idempotent_replay",
    "cadence_blocked",
]


def new_publish_tx_id() -> str:
    return f"pub-{uuid.uuid4().hex[:20]}"


def append_journal(
    runtime_dir: str | None,
    *,
    tx_id: str,
    draft_id: int,
    state: PublishState,
    idempotency_key: str = "",
    channel_message_id: int | None = None,
    error: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "tx_id": tx_id,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "ts_unix": round(time.time(), 3),
        "draft_id": int(draft_id),
        "state": state,
        "idempotency_key": (idempotency_key or "")[:120],
        "channel_message_id": channel_message_id,
        "error": (error or "")[:300],
    }
    if extra:
        entry["extra"] = extra
    path = publish_journal_path(runtime_dir)
    line = json.dumps(entry, ensure_ascii=False, default=str) + "\n"
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)
        _apply_retention(path)
    return entry


def _apply_retention(path: Path) -> None:
    if not path.is_file():
        return
    try:
        if path.stat().st_size <= _MAX_BYTES:
            with path.open(encoding="utf-8") as fh:
                if sum(1 for _ in fh) <= _MAX_LINES:
                    return
        with path.open(encoding="utf-8") as fh:
            lines = fh.readlines()
        keep = lines[-_MAX_LINES:]
        while keep and sum(len(x.encode()) for x in keep) > _MAX_BYTES:
            keep = keep[1:]
        path.write_text("".join(keep), encoding="utf-8")
    except OSError:
        pass


def _read_all(runtime_dir: str | None) -> list[dict[str, Any]]:
    path = publish_journal_path(runtime_dir)
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
                if isinstance(row, dict):
                    rows.append(row)
    except OSError:
        pass
    return rows


def find_finalized_for_draft(runtime_dir: str | None, draft_id: int) -> dict[str, Any] | None:
    for row in reversed(_read_all(runtime_dir)):
        if int(row.get("draft_id") or 0) != draft_id:
            continue
        if row.get("state") == "finalized":
            return row
    return None


def find_by_idempotency_key(runtime_dir: str | None, key: str) -> dict[str, Any] | None:
    if not key:
        return None
    for row in reversed(_read_all(runtime_dir)):
        if row.get("idempotency_key") == key and row.get("state") == "finalized":
            return row
    return None


def find_inflight(runtime_dir: str | None, *, max_age_sec: float = 600.0) -> list[dict[str, Any]]:
    terminal = {"finalized", "failed", "cadence_blocked", "idempotent_replay"}
    now = time.time()
    inflight: dict[int, dict[str, Any]] = {}
    for row in _read_all(runtime_dir):
        did = int(row.get("draft_id") or 0)
        if not did:
            continue
        st = str(row.get("state") or "")
        if st in terminal:
            inflight.pop(did, None)
            continue
        ts = float(row.get("ts_unix") or 0)
        if now - ts <= max_age_sec:
            inflight[did] = row
    return list(inflight.values())


def journal_tail(runtime_dir: str | None, *, limit: int = 50) -> list[dict[str, Any]]:
    return list(reversed(_read_all(runtime_dir)[-limit:]))


def reset_journal_for_tests(runtime_dir: str) -> None:
    p = publish_journal_path(runtime_dir)
    if p.is_file():
        p.unlink()
