"""Per-source health scoring (success, dedup, failure, latency)."""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any

from ops.pipeline.paths import source_health_path

_lock = threading.RLock()
_WINDOW = int(os.getenv("OPS_SOURCE_HEALTH_WINDOW", "100"))


def _load(runtime_dir: str | None) -> dict[str, Any]:
    p = source_health_path(runtime_dir)
    if not p.is_file():
        return {"version": 1, "sources": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "sources": {}}
    data.setdefault("sources", {})
    return data


def _save(runtime_dir: str | None, data: dict[str, Any]) -> None:
    source_health_path(runtime_dir).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _row(data: dict[str, Any], source: str) -> dict[str, Any]:
    key = (source or "").strip().lower()
    sources = data.setdefault("sources", {})
    row = sources.get(key)
    if not isinstance(row, dict):
        row = {"events": [], "score": 50.0}
        sources[key] = row
    return row


def record_event(
    runtime_dir: str | None,
    source: str,
    *,
    ok: bool,
    latency_ms: float = 0.0,
    dedup: bool = False,
) -> float:
    with _lock:
        data = _load(runtime_dir)
        row = _row(data, source)
        events = list(row.get("events") or [])
        events.append(
            {
                "ok": ok,
                "dedup": dedup,
                "latency_ms": round(latency_ms, 2),
                "ts": time.time(),
            }
        )
        row["events"] = events[-_WINDOW:]
        row["score"] = _compute_score(row)
        _save(runtime_dir, data)
        return float(row["score"])


def _compute_score(row: dict[str, Any]) -> float:
    events = list(row.get("events") or [])
    if not events:
        return 50.0
    ok_n = sum(1 for e in events if e.get("ok"))
    dedup_n = sum(1 for e in events if e.get("dedup"))
    fail_n = len(events) - ok_n
    success_rate = ok_n / len(events)
    dedup_rate = dedup_n / len(events)
    failure_rate = fail_n / len(events)
    latencies = [float(e.get("latency_ms") or 0) for e in events if e.get("ok")]
    avg_lat = sum(latencies) / max(1, len(latencies))
    lat_score = max(0.0, 1.0 - min(avg_lat, 30_000.0) / 30_000.0)
    raw = (
        0.45 * success_rate
        + 0.25 * lat_score
        + 0.20 * (1.0 - failure_rate)
        + 0.10 * (1.0 - min(1.0, dedup_rate * 2))
    )
    return round(max(0.0, min(100.0, raw * 100)), 2)


def get_source_score(runtime_dir: str | None, source: str) -> float:
    with _lock:
        data = _load(runtime_dir)
        row = _row(data, source)
        return float(row.get("score") or 50.0)


def export_health(runtime_dir: str | None) -> dict[str, Any]:
    with _lock:
        return _load(runtime_dir)
