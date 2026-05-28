"""Rolling runtime health metrics for long-uptime VPS burn-in (diagnostics only)."""

from __future__ import annotations

import json
import logging
import os
import platform
import resource
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from utils.structured_log import log_event

logger = logging.getLogger(__name__)

_lock = threading.RLock()
_boot_mono = time.monotonic()
_baseline_rss_mb: float | None = None

_tick_durations_sec: deque[float] = deque(maxlen=64)
_publish_latency_ms: deque[float] = deque(maxlen=32)
_openai_latency_ms: deque[float] = deque(maxlen=32)
_db_latency_ms: deque[float] = deque(maxlen=32)
_retry_timestamps: deque[float] = deque(maxlen=200)
_rss_mb_samples: deque[tuple[float, float]] = deque(maxlen=96)
_queue_depth_samples: deque[int] = deque(maxlen=32)
_scheduler_lag_ms: deque[float] = deque(maxlen=32)
_event_loop_block_ms: deque[float] = deque(maxlen=16)


def reset_runtime_health_for_tests() -> None:
    global _baseline_rss_mb, _boot_mono
    with _lock:
        _boot_mono = time.monotonic()
        _baseline_rss_mb = None
        _tick_durations_sec.clear()
        _publish_latency_ms.clear()
        _openai_latency_ms.clear()
        _db_latency_ms.clear()
        _retry_timestamps.clear()
        _rss_mb_samples.clear()
        _queue_depth_samples.clear()
        _scheduler_lag_ms.clear()
        _event_loop_block_ms.clear()


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    idx = min(len(s) - 1, max(0, int(len(s) * pct)))
    return round(s[idx], 2)


def _process_rss_mb() -> float | None:
    try:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        rss = float(usage.ru_maxrss)
        if sys.platform == "darwin":
            return round(rss / (1024 * 1024), 2)
        return round(rss / 1024, 2)
    except Exception:
        return None


def record_tick_duration(sec: float) -> None:
    if sec <= 0:
        return
    with _lock:
        _tick_durations_sec.append(sec)


def record_publish_latency_ms(ms: float) -> None:
    with _lock:
        _publish_latency_ms.append(max(0.0, ms))


def record_openai_latency_ms(ms: float) -> None:
    with _lock:
        _openai_latency_ms.append(max(0.0, ms))


def record_db_latency_ms(ms: float) -> None:
    with _lock:
        _db_latency_ms.append(max(0.0, ms))


def record_retry_event() -> None:
    with _lock:
        _retry_timestamps.append(time.monotonic())


def record_queue_depth(depth: int) -> None:
    with _lock:
        _queue_depth_samples.append(max(0, int(depth)))


def record_scheduler_lag_ms(ms: float) -> None:
    with _lock:
        _scheduler_lag_ms.append(max(0.0, ms))


def record_event_loop_block_ms(ms: float) -> None:
    with _lock:
        _event_loop_block_ms.append(max(0.0, ms))


def _retry_rate_per_min() -> float:
    cutoff = time.monotonic() - 60.0
    with _lock:
        n = sum(1 for t in _retry_timestamps if t >= cutoff)
    return round(float(n), 2)


def _memory_drift_mb() -> float | None:
    global _baseline_rss_mb
    rss = _process_rss_mb()
    if rss is None:
        return None
    with _lock:
        if _baseline_rss_mb is None:
            _baseline_rss_mb = rss
        _rss_mb_samples.append((time.monotonic(), rss))
    return round(rss - _baseline_rss_mb, 2)


def collect_health_snapshot(*, settings: Any | None = None) -> dict[str, Any]:
    """Build one health snapshot from in-process rolling buffers + activity."""
    from app.runtime_activity import activity_snapshot, exception_count_in_window

    rss = _process_rss_mb()
    drift = _memory_drift_mb()

    with _lock:
        tick_list = list(_tick_durations_sec)
        pub_list = list(_publish_latency_ms)
        oai_list = list(_openai_latency_ms)
        db_list = list(_db_latency_ms)
        q_depth = _queue_depth_samples[-1] if _queue_depth_samples else 0
        sched_lag = _scheduler_lag_ms[-1] if _scheduler_lag_ms else None
        el_block = max(_event_loop_block_ms) if _event_loop_block_ms else None

    avg_tick = round(sum(tick_list) / len(tick_list), 3) if tick_list else None
    p95_tick = _percentile(tick_list, 0.95)
    avg_pub = round(sum(pub_list) / len(pub_list), 1) if pub_list else None
    avg_oai = round(sum(oai_list) / len(oai_list), 1) if oai_list else None
    avg_db = round(sum(db_list) / len(db_list), 1) if db_list else None

    activity = activity_snapshot()
    since_tick = activity.get("seconds_since_scheduler_tick")
    scheduler_delay_ms = round(float(since_tick) * 1000, 1) if since_tick is not None else sched_lag

    degradation_flags: list[str] = []
    if drift is not None and drift > float(os.getenv("RUNTIME_HEALTH_RSS_DRIFT_MB", "256")):
        degradation_flags.append("memory_drift_high")
    if p95_tick is not None and p95_tick > float(os.getenv("RUNTIME_HEALTH_TICK_P95_SEC", "600")):
        degradation_flags.append("tick_duration_p95_high")
    if _retry_rate_per_min() > float(os.getenv("RUNTIME_HEALTH_RETRY_PER_MIN", "12")):
        degradation_flags.append("retry_rate_high")
    if avg_oai is not None and avg_oai > float(os.getenv("RUNTIME_HEALTH_OPENAI_MS", "45000")):
        degradation_flags.append("openai_latency_high")
    if avg_pub is not None and avg_pub > float(os.getenv("RUNTIME_HEALTH_PUBLISH_MS", "30000")):
        degradation_flags.append("publish_latency_high")
    if scheduler_delay_ms is not None and scheduler_delay_ms > float(
        os.getenv("RUNTIME_HEALTH_SCHEDULER_LAG_MS", "120000")
    ):
        degradation_flags.append("scheduler_lag_high")
    if exception_count_in_window(300.0) > int(os.getenv("RUNTIME_HEALTH_EXCEPTIONS_5M", "8")):
        degradation_flags.append("exception_burst")
    if el_block is not None and el_block > float(os.getenv("RUNTIME_HEALTH_EVENT_LOOP_BLOCK_MS", "500")):
        degradation_flags.append("event_loop_block")

    try:
        from app.observability.ops_metrics import ops_snapshot

        ops = ops_snapshot()
        fast_q = int(ops.get("fast_lane_queue_depth") or 0)
        std_q = int(ops.get("standard_lane_queue_depth") or 0)
        slow_q = int(ops.get("slow_lane_queue_depth") or 0)
        q_depth = fast_q + std_q + slow_q
        cap = int(os.getenv("OPS_MAX_QUEUE_DEPTH", "256"))
        if q_depth >= int(cap * float(os.getenv("RUNTIME_HEALTH_QUEUE_CAP_RATIO", "0.75"))):
            degradation_flags.append("queue_backlog_high")
    except Exception:
        pass

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": round(time.monotonic() - _boot_mono, 1),
        "rss_mb": rss,
        "rss_drift_mb": drift,
        "avg_tick_duration_sec": avg_tick,
        "p95_tick_duration_sec": p95_tick,
        "queue_depth": q_depth,
        "retry_rate_per_min": _retry_rate_per_min(),
        "openai_latency_ms": avg_oai,
        "publish_latency_ms": avg_pub,
        "scheduler_delay_ms": scheduler_delay_ms,
        "db_latency_ms": avg_db,
        "event_loop_block_ms": el_block,
        "degradation_flags": degradation_flags,
        "exception_count_5m": exception_count_in_window(300.0),
        "platform": platform.system(),
    }


def health_jsonl_path(runtime_dir: str) -> Path:
    return Path(runtime_dir).expanduser().resolve() / "runtime_health.jsonl"


def persist_health_snapshot(runtime_dir: str, snapshot: dict[str, Any]) -> None:
    path = health_jsonl_path(runtime_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(snapshot, ensure_ascii=False) + "\n")
    except OSError as exc:
        log_event(logger, "runtime_health.persist_failed", error=repr(exc)[:120])


def load_health_snapshots(runtime_dir: str, *, limit: int = 200) -> list[dict[str, Any]]:
    path = health_jsonl_path(runtime_dir)
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").strip().splitlines()
    out: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def sample_and_persist(runtime_dir: str, *, settings: Any | None = None) -> dict[str, Any]:
    snap = collect_health_snapshot(settings=settings)
    persist_health_snapshot(runtime_dir, snap)
    return snap
