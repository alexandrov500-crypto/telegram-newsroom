"""Per-stage resource accounting with hourly/daily rollups."""

from __future__ import annotations

import os
import time
from typing import Any

from editorial.intelligence_store import load_json, save_json
from ops.economics.paths import resources_daily_path, resources_hourly_path


def _hour_key(ts: float | None = None) -> str:
    t = time.gmtime(ts or time.time())
    return time.strftime("%Y-%m-%dT%H", t)


def _day_key(ts: float | None = None) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(ts or time.time()))


def _merge_stage(row: dict[str, Any], stage: str, delta: dict[str, Any]) -> None:
    st = dict(row.get("stages") or {})
    cur = dict(st.get(stage) or {})
    for k, v in delta.items():
        if k in ("duration_sec", "cost_usd", "tokens", "bytes", "count"):
            cur[k] = round(float(cur.get(k) or 0) + float(v), 6)
    st[stage] = cur
    row["stages"] = st


def record_resource(
    runtime_dir: str,
    *,
    stage: str,
    duration_sec: float = 0.0,
    tokens: int = 0,
    cost_usd: float = 0.0,
    bytes_delta: int = 0,
    count: int = 1,
    extra: dict[str, Any] | None = None,
) -> None:
    """Record consumption for a pipeline stage (summarize, scoring, publish, etc.)."""
    delta = {
        "duration_sec": max(0.0, duration_sec),
        "tokens": max(0, int(tokens)),
        "cost_usd": max(0.0, float(cost_usd)),
        "bytes": max(0, int(bytes_delta)),
        "count": max(0, int(count)),
    }
    now = time.time()
    for path_fn, key_fn in ((resources_hourly_path, _hour_key), (resources_daily_path, _day_key)):
        path = path_fn(runtime_dir)
        data = load_json(path, {"version": 1, "buckets": {}})
        buckets = dict(data.get("buckets") or {})
        k = key_fn(now)
        row = dict(buckets.get(k) or {"updated_at": ""})
        _merge_stage(row, stage[:40], delta)
        if extra:
            ex = dict(row.get("extra") or {})
            ex[stage] = extra
            row["extra"] = ex
        row["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
        buckets[k] = row
        # trim old buckets
        max_h = int(os.getenv("ECONOMICS_HOURLY_BUCKETS_MAX", "168"))
        max_d = int(os.getenv("ECONOMICS_DAILY_BUCKETS_MAX", "90"))
        keys = sorted(buckets.keys(), reverse=True)
        limit = max_h if path_fn == resources_hourly_path else max_d
        data["buckets"] = {x: buckets[x] for x in keys[:limit]}
        save_json(path, data)


def resources_payload(runtime_dir: str, *, hours: int = 48) -> dict[str, Any]:
    from utils.metrics import export_snapshot

    hourly = load_json(resources_hourly_path(runtime_dir), {"buckets": {}})
    daily = load_json(resources_daily_path(runtime_dir), {"buckets": {}})
    snap = export_snapshot()
    ctr = dict(snap.get("counters") or {})
    gauges = dict(snap.get("gauges") or {})
    h_buckets = dict(hourly.get("buckets") or {})
    d_buckets = dict(daily.get("buckets") or {})
    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "hourly": {k: h_buckets[k] for k in sorted(h_buckets.keys(), reverse=True)[:hours]},
        "daily": {k: d_buckets[k] for k in sorted(d_buckets.keys(), reverse=True)[:30]},
        "live_counters": {
            "ai_input_tokens": int(ctr.get("ai_input_tokens") or 0),
            "ai_output_tokens": int(ctr.get("ai_output_tokens") or 0),
            "ai_cost_micro_usd": int(ctr.get("ai_cost_micro_usd") or 0),
            "ai_cluster_calls": int(ctr.get("ai_cluster_calls") or 0),
            "scoring_failures_total": int(ctr.get("scoring_failures_total") or 0),
        },
        "live_gauges": {
            "queue_depth": gauges.get("queue_depth"),
            "ai_last_cluster_latency_sec": gauges.get("ai_last_cluster_latency_sec"),
        },
    }


def snapshot_storage_bytes(runtime_dir: str) -> dict[str, int]:
    root = __import__("pathlib").Path(runtime_dir).expanduser().resolve()
    out: dict[str, int] = {}
    for name in ("incidents", "full_snapshots", "editorial", "economics", "ops", "analytics"):
        p = root / name if name != "editorial" else root / "editorial"
        if name == "editorial":
            p = root / "editorial"
        else:
            p = root / name
        if not p.exists():
            out[name] = 0
            continue
        total = 0
        if p.is_file():
            total = p.stat().st_size
        else:
            for f in p.rglob("*"):
                if f.is_file():
                    try:
                        total += f.stat().st_size
                    except OSError:
                        pass
        out[name] = total
    # root json/jsonl
    loose = 0
    for f in root.glob("*"):
        if f.is_file() and f.suffix in {".json", ".jsonl", ".txt"}:
            try:
                loose += f.stat().st_size
            except OSError:
                pass
    out["runtime_loose_files"] = loose
    out["total_estimated"] = sum(out.values())
    return out
