"""Temporary suppression memory + duplicate-burst counters (JSON, TTL)."""

from __future__ import annotations

import time
from typing import Any

from editorial.intelligence_store import load_json, save_json, suppression_state_path


def _path(runtime_dir: str | None) -> Any:
    return suppression_state_path(runtime_dir)


def is_suppression_active(runtime_dir: str | None, key: str) -> bool:
    k = str(key or "").strip()
    if not k:
        return False
    data = load_json(_path(runtime_dir), {"version": 1, "entries": {}, "duplicate_burst": {}})
    ent = data.get("entries") or {}
    row = ent.get(k)
    if not isinstance(row, dict):
        return False
    until = float(row.get("until") or 0.0)
    return time.time() < until


def record_suppression_ttl(runtime_dir: str | None, key: str, ttl_sec: float, *, reason: str = "") -> None:
    k = str(key or "").strip()
    if not k:
        return
    ttl = max(1.0, min(float(ttl_sec), 86400.0 * 3))
    path = _path(runtime_dir)
    data = load_json(path, {"version": 1, "entries": {}, "duplicate_burst": {}})
    ent = dict(data.get("entries") or {})
    ent[k] = {"until": time.time() + ttl, "reason": reason[:200], "ts": time.time()}
    # cap size
    items = sorted(ent.items(), key=lambda kv: float(kv[1].get("until") or 0), reverse=True)[:200]
    data["entries"] = dict(items)
    save_json(path, data)


def bump_duplicate_burst(runtime_dir: str | None, *, window_sec: float = 900.0) -> int:
    """Increment burst counter inside window; returns current count."""
    path = _path(runtime_dir)
    data = load_json(path, {"version": 1, "entries": {}, "duplicate_burst": {}})
    burst = dict(data.get("duplicate_burst") or {})
    now = time.time()
    start = float(burst.get("window_start") or 0.0)
    if now - start > window_sec:
        burst = {"window_start": now, "count": 0}
    burst["count"] = int(burst.get("count") or 0) + 1
    data["duplicate_burst"] = burst
    save_json(path, data)
    return int(burst["count"])


def duplicate_burst_count(runtime_dir: str | None) -> int:
    data = load_json(_path(runtime_dir), {"version": 1, "entries": {}, "duplicate_burst": {}})
    burst = data.get("duplicate_burst") or {}
    return int(burst.get("count") or 0)


def reset_duplicate_burst(runtime_dir: str | None) -> None:
    path = _path(runtime_dir)
    data = load_json(path, {"version": 1, "entries": {}, "duplicate_burst": {}})
    data["duplicate_burst"] = {"window_start": 0.0, "count": 0}
    save_json(path, data)


def prune_expired_suppression_entries(runtime_dir: str | None) -> dict[str, Any]:
    """Remove TTL-expired suppression keys; returns counts for ops logs."""
    now = time.time()
    path = _path(runtime_dir)
    data = load_json(path, {"version": 1, "entries": {}, "duplicate_burst": {}})
    ent = dict(data.get("entries") or {})
    before = len(ent)
    kept: dict[str, Any] = {}
    for k, v in ent.items():
        if not isinstance(v, dict):
            continue
        if float(v.get("until") or 0.0) >= now:
            kept[k] = v
    data["entries"] = kept
    save_json(path, data)
    return {"removed": before - len(kept), "remaining": len(kept)}


def reset_suppression_state_emergency(runtime_dir: str | None) -> dict[str, Any]:
    """
    Operator escape hatch: clears TTL suppressions and duplicate-burst counter.
    Does not touch topic memory or cadence files.
    """
    path = _path(runtime_dir)
    data: dict[str, Any] = {"version": 1, "entries": {}, "duplicate_burst": {"window_start": 0.0, "count": 0}}
    save_json(path, data)
    return {"path": str(path), "cleared": True}
