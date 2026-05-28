"""Story suppression — dampen near-duplicate micro-news in the ingest stream."""

from __future__ import annotations

import json
import re
import threading
from collections import deque
from pathlib import Path
from typing import Any

from ops.pipeline.paths import runtime_root

_SIMILARITY_THRESHOLD = 0.87
_RING_SIZE = 10
_lock = threading.Lock()
_recent_by_runtime: dict[str, deque[set[str]]] = {}


def _tokenize(text: str) -> set[str]:
    words = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9]{4,}", (text or "").lower())
    return set(words)


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _ring_key(runtime_dir: str | None) -> str:
    return str(runtime_dir or "default")


def _load_ring_from_disk(runtime_dir: str | None) -> deque[set[str]]:
    path = runtime_root(runtime_dir) / "suppression_recent.json"
    ring: deque[set[str]] = deque(maxlen=_RING_SIZE)
    if not path.is_file():
        return ring
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            for entry in data[-_RING_SIZE:]:
                if isinstance(entry, list):
                    ring.append(set(entry))
    except Exception:
        pass
    return ring


def _persist_ring(runtime_dir: str | None, ring: deque[set[str]]) -> None:
    path = runtime_root(runtime_dir) / "suppression_recent.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [sorted(tokens) for tokens in ring]
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def should_suppress(
    item: dict[str, Any],
    *,
    runtime_dir: str | None = None,
    threshold: float = _SIMILARITY_THRESHOLD,
) -> tuple[bool, float]:
    """
    Returns (suppress, max_similarity).
    Compares against last N items in the runtime ring buffer.
    """
    text = str(item.get("text") or item.get("content") or "")
    if len(text.strip()) < 40:
        return False, 0.0

    tokens = _tokenize(text)
    if len(tokens) < 6:
        return False, 0.0

    key = _ring_key(runtime_dir)
    with _lock:
        ring = _recent_by_runtime.get(key)
        if ring is None:
            ring = _load_ring_from_disk(runtime_dir)
            _recent_by_runtime[key] = ring

        max_sim = 0.0
        for prev in ring:
            sim = _jaccard(tokens, prev)
            max_sim = max(max_sim, sim)
            if sim > threshold:
                return True, round(sim, 4)

        ring.append(tokens)
        _persist_ring(runtime_dir, ring)

    return False, round(max_sim, 4)
