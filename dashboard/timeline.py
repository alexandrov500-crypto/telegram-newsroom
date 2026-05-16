"""Lightweight append-only operational timeline (JSON file, bounded)."""

from __future__ import annotations

import json
import time
from typing import Any

from editorial.intelligence_store import load_json, operational_timeline_path, save_json


def _trim_payload(payload: dict[str, Any], *, max_json_chars: int = 10_000) -> dict[str, Any]:
    try:
        raw = json.dumps(payload, default=str)
    except TypeError:
        return {"_error": "payload_not_json_serializable"}
    if len(raw) <= max_json_chars:
        return dict(payload)
    return {"_truncated": True, "preview": raw[: max_json_chars - 80]}


def append_timeline_event(
    runtime_dir: str | None,
    kind: str,
    payload: dict[str, Any],
    *,
    max_entries: int = 240,
) -> None:
    path = operational_timeline_path(runtime_dir)
    data = load_json(path, {"version": 1, "events": []})
    evs = list(data.get("events") or [])
    row = {"ts": time.time(), "kind": str(kind)[:120], "payload": _trim_payload(dict(payload))}
    evs.insert(0, row)
    data["events"] = evs[:max_entries]
    save_json(path, data)


def load_timeline_tail(runtime_dir: str | None, *, limit: int = 48) -> list[dict[str, Any]]:
    path = operational_timeline_path(runtime_dir)
    data = load_json(path, {"version": 1, "events": []})
    evs = [x for x in (data.get("events") or []) if isinstance(x, dict)]
    return evs[: max(1, min(limit, 500))]


def compact_operational_timeline(
    runtime_dir: str | None,
    *,
    max_entries: int = 240,
    max_age_sec: float | None = None,
) -> dict[str, Any]:
    """
    Trim timeline by optional age and hard entry cap (operator / compaction pass).
    Events are stored newest-first (same convention as ``append_timeline_event``).
    """
    path = operational_timeline_path(runtime_dir)
    data = load_json(path, {"version": 1, "events": []})
    evs = [x for x in (data.get("events") or []) if isinstance(x, dict)]
    now = time.time()
    if max_age_sec is not None:
        ma = float(max_age_sec)
        evs = [e for e in evs if now - float(e.get("ts") or 0.0) <= ma]
    before = len(evs)
    evs = evs[: max(1, min(int(max_entries), 2000))]
    data["events"] = evs
    save_json(path, data)
    return {"path": str(path), "before": before, "kept": len(evs), "max_entries": int(max_entries)}
