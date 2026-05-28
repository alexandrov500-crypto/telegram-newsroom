"""Lightweight editorial memory (JSON, runtime_state_dir)."""

from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from typing import Any

_lock = threading.RLock()
_MAX_RECENT = 80
_MAX_TOPICS = 200

_STOP = frozenset(
    "и в на с по для что это как из от к о а the a an of to in on for is at".split()
)


def _path(runtime_dir: str) -> Path:
    p = Path(runtime_dir).expanduser().resolve() / "editorial" / "memory.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _load(runtime_dir: str) -> dict[str, Any]:
    path = _path(runtime_dir)
    if not path.is_file():
        return {"version": 1, "topics": {}, "recent": [], "phrases": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"version": 1, "topics": {}, "recent": [], "phrases": {}}
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "topics": {}, "recent": [], "phrases": {}}


def _save(runtime_dir: str, data: dict[str, Any]) -> None:
    _path(runtime_dir).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def topic_key_from_text(text: str, *, fallback: str = "") -> str:
    """Deterministic topic bucket (no ML)."""
    words = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9]{4,}", (text or "").lower())
    freq: dict[str, int] = {}
    for w in words:
        if w in _STOP:
            continue
        freq[w] = freq.get(w, 0) + 1
    if not freq:
        return (fallback or "general")[:64]
    top = sorted(freq.items(), key=lambda x: (-x[1], x[0]))[:3]
    return "_".join(k for k, _ in top)[:64]


def memory_snapshot(runtime_dir: str) -> dict[str, Any]:
    with _lock:
        return _load(runtime_dir)


def record_storyline_memory(
    runtime_dir: str,
    *,
    topic_key: str,
    headline: str = "",
    body_preview: str = "",
    sources: list[str] | None = None,
    draft_id: int | None = None,
) -> None:
    """Call after successful publish (advisory store)."""
    now = time.time()
    key = (topic_key or "general")[:64]
    with _lock:
        data = _load(runtime_dir)
        topics = dict(data.get("topics") or {})
        row = dict(topics.get(key) or {})
        row["last_published_unix"] = now
        row["publish_count"] = int(row.get("publish_count") or 0) + 1
        row["last_headline"] = (headline or "")[:200]
        row["last_preview"] = (body_preview or "")[:280]
        topics[key] = row
        if len(topics) > _MAX_TOPICS:
            oldest = sorted(topics.items(), key=lambda x: float(x[1].get("last_published_unix") or 0))[:20]
            for k, _ in oldest:
                topics.pop(k, None)
        recent = list(data.get("recent") or [])
        recent.append(
            {
                "topic_key": key,
                "unix": now,
                "draft_id": draft_id,
                "sources": (sources or [])[:8],
            }
        )
        recent = recent[-_MAX_RECENT:]
        phrases = dict(data.get("phrases") or {})
        for pat in _extract_opener_phrases(body_preview or headline):
            phrases[pat] = int(phrases.get(pat) or 0) + 1
        data["topics"] = topics
        data["recent"] = recent
        data["phrases"] = phrases
        _save(runtime_dir, data)


def count_topic_in_window(runtime_dir: str, topic_key: str, *, hours: float = 24.0) -> int:
    cutoff = time.time() - hours * 3600.0
    with _lock:
        data = _load(runtime_dir)
    n = 0
    for row in data.get("recent") or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("topic_key")) != topic_key:
            continue
        if float(row.get("unix") or 0) >= cutoff:
            n += 1
    return n


def hours_since_topic(runtime_dir: str, topic_key: str) -> float | None:
    with _lock:
        topics = (_load(runtime_dir).get("topics") or {})
    row = topics.get(topic_key)
    if not isinstance(row, dict):
        return None
    ts = float(row.get("last_published_unix") or 0)
    if ts <= 0:
        return None
    return max(0.0, (time.time() - ts) / 3600.0)


def _extract_opener_phrases(text: str) -> list[str]:
    t = (text or "").strip().lower()[:120]
    if not t:
        return []
    first = t.split(".")[0].strip()
    if len(first) < 12:
        return []
    return [first[:80]]


def recent_opener_phrases(runtime_dir: str, *, limit: int = 12) -> list[str]:
    with _lock:
        phrases = (_load(runtime_dir).get("phrases") or {})
    items = sorted(phrases.items(), key=lambda x: -int(x[1]))[:limit]
    return [k for k, v in items if int(v) >= 2]
