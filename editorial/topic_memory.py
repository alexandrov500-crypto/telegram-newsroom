"""Short-term topic memory (counts, cooldown, saturation) — JSON file, no vectors."""

from __future__ import annotations

import hashlib
import time
from typing import Any

from editorial.intelligence_store import load_json, save_json, topic_memory_path


def _topic_key(hint: str) -> str:
    h = " ".join((hint or "").lower().split())[:200]
    if not h:
        return "unknown"
    return hashlib.sha256(h.encode("utf-8")).hexdigest()[:20]


def bump_topic(
    runtime_dir: str | None,
    *,
    topic_hint: str,
    fingerprint: str,
    max_topics: int = 200,
    window_hours: float = 168.0,
) -> dict[str, Any]:
    path = topic_memory_path(runtime_dir)
    data = load_json(path, {"version": 1, "topics": {}})
    topics: dict[str, Any] = dict(data.get("topics") or {})
    key = _topic_key(topic_hint)
    now = time.time()
    row = topics.get(key) or {"hint": topic_hint[:200], "count": 0, "last_ts": now, "fingerprints": []}
    row["hint"] = topic_hint[:200]
    row["count"] = int(row.get("count") or 0) + 1
    row["last_ts"] = now
    fps = list(row.get("fingerprints") or [])
    fps.insert(0, fingerprint)
    row["fingerprints"] = fps[:32]
    topics[key] = row
    # prune stale
    cutoff = now - window_hours * 3600.0
    trimmed: dict[str, Any] = {}
    for k, v in topics.items():
        if not isinstance(v, dict):
            continue
        if float(v.get("last_ts") or 0) >= cutoff:
            trimmed[k] = v
    # cap size by recency
    items = sorted(trimmed.items(), key=lambda kv: float(kv[1].get("last_ts") or 0), reverse=True)[:max_topics]
    data["topics"] = {k: v for k, v in items}
    save_json(path, data)
    return row


def topic_saturation(row: dict[str, Any] | None, *, burst_threshold: int = 8) -> tuple[bool, str | None]:
    if not row:
        return False, None
    c = int(row.get("count") or 0)
    if c >= burst_threshold:
        return True, f"topic_count>{burst_threshold}"
    return False, None


def topic_cooldown_active(row: dict[str, Any] | None, *, cooldown_sec: float = 900.0, now: float | None = None) -> bool:
    if not row:
        return False
    t = float(now or time.time())
    return (t - float(row.get("last_ts") or 0)) < cooldown_sec and int(row.get("count") or 0) >= 3


def export_topic_snapshot(runtime_dir: str | None, *, limit: int = 40) -> list[dict[str, Any]]:
    data = load_json(topic_memory_path(runtime_dir), {"version": 1, "topics": {}})
    topics = data.get("topics") or {}
    if not isinstance(topics, dict):
        return []
    rows = []
    for k, v in topics.items():
        if not isinstance(v, dict):
            continue
        rows.append({"key": k, **v})
    rows.sort(key=lambda r: float(r.get("last_ts") or 0), reverse=True)
    return rows[:limit]
