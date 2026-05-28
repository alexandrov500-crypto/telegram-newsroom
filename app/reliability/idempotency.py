"""Deterministic idempotency index (JSONL) + publish journal integration."""

from __future__ import annotations

import hashlib
import json
import threading
import time
from typing import Any

from ops.pipeline.paths import idempotency_index_path
from ops.resilience.publish_journal import find_by_idempotency_key

_lock = threading.RLock()


def build_publish_idempotency_key(
    *,
    source_id: str,
    external_message_id: int | str,
    content_hash: str,
    draft_id: int | None = None,
) -> str:
    """hash(source_id + external_message_id + content_hash) as required."""
    src = (source_id or "").strip().lower()
    ext = str(external_message_id)
    ch = (content_hash or "").strip()
    if draft_id is not None:
        raw = f"pub|{src}|{ext}|{ch}|draft:{int(draft_id)}"
    else:
        raw = f"pub|{src}|{ext}|{ch}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_content_hash(text: str) -> str:
    from utils.text_hash import normalize_text_for_match

    norm = normalize_text_for_match(text or "")
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:32]


def is_idempotency_processed(runtime_dir: str | None, key: str) -> bool:
    if not key:
        return False
    if find_by_idempotency_key(runtime_dir, key):
        return True
    path = idempotency_index_path(runtime_dir)
    if not path.is_file():
        return False
    try:
        with path.open(encoding="utf-8") as fh:
            for line in reversed(fh.readlines()[-500:]):
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if row.get("key") == key and row.get("state") == "finalized":
                    return True
    except OSError:
        pass
    return False


def mark_idempotency_processed(
    runtime_dir: str | None,
    key: str,
    *,
    draft_id: int,
    channel_message_id: int | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    if not key:
        return
    row = {
        "ts_unix": round(time.time(), 3),
        "key": key[:160],
        "state": "finalized",
        "draft_id": int(draft_id),
        "channel_message_id": channel_message_id,
        "extra": extra or {},
    }
    path = idempotency_index_path(runtime_dir)
    line = json.dumps(row, ensure_ascii=False, default=str) + "\n"
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)
