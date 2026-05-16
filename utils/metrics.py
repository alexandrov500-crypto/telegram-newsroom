from __future__ import annotations

import logging
import threading
from typing import Any

from utils.structured_log import log_event

logger = logging.getLogger(__name__)

_lock = threading.RLock()
_counts: dict[str, int] = {
    "posts_collected": 0,
    "clusters_created": 0,
    "drafts_generated": 0,
    "drafts_created": 0,
    "drafts_approved": 0,
    "drafts_rejected": 0,
    "drafts_published": 0,
    "publish_failures": 0,
    "publishes": 0,
    "openai_failures": 0,
    "openai_retries": 0,
    "skipped_duplicates": 0,
    "skipped_intelligence_suppress": 0,
    "cadence_deferred_cluster": 0,
    "cadence_blocked_publish": 0,
    "telethon_reconnects": 0,
    "telethon_flood_waits": 0,
    "telegram_api_failures": 0,
    "publish_retries": 0,
    "publish_lock_contention": 0,
    "publish_lock_strict_denied": 0,
    "publish_lock_redis_fallback": 0,
    "publish_lock_stale_suspected": 0,
    "worker_retry_safe_reorders": 0,
    "admin_notify_failures": 0,
    "draft_edits": 0,
    "scheduled_publish_fired": 0,
}

_gauges: dict[str, float] = {}

_pipeline_sec_sum = 0.0
_pipeline_sec_count = 0


def inc(metric: str, delta: int = 1) -> None:
    if delta <= 0:
        return
    with _lock:
        _counts[metric] = _counts.get(metric, 0) + delta


def set_gauge(name: str, value: float) -> None:
    with _lock:
        _gauges[str(name)] = float(value)


def snapshot() -> dict[str, int]:
    with _lock:
        return dict(_counts)


def reset_metrics() -> None:
    """Reset counters, gauges, and pipeline duration aggregates (tests / admin)."""
    global _pipeline_sec_sum, _pipeline_sec_count
    with _lock:
        for k in list(_counts.keys()):
            _counts[k] = 0
        _gauges.clear()
        _pipeline_sec_sum = 0.0
        _pipeline_sec_count = 0


def export_snapshot() -> dict[str, Any]:
    """JSON-friendly metrics export (counters + gauges + timing aggregates)."""
    with _lock:
        avg = None
        if _pipeline_sec_count > 0:
            avg = _pipeline_sec_sum / _pipeline_sec_count
        return {
            "counters": dict(_counts),
            "gauges": dict(_gauges),
            "pipeline_duration_sum_sec": round(_pipeline_sec_sum, 6),
            "pipeline_duration_sample_count": int(_pipeline_sec_count),
            "pipeline_duration_avg_sec": round(avg, 6) if avg is not None else None,
        }


def record_pipeline_duration(sec: float) -> None:
    if sec <= 0:
        return
    global _pipeline_sec_sum, _pipeline_sec_count
    with _lock:
        _pipeline_sec_sum += sec
        _pipeline_sec_count += 1


def avg_pipeline_duration_sec() -> float | None:
    with _lock:
        if _pipeline_sec_count <= 0:
            return None
        return _pipeline_sec_sum / _pipeline_sec_count


def log_pipeline_metrics(logger: logging.Logger) -> None:
    snap = snapshot()
    snap["retries"] = snap.get("openai_retries", 0)
    avg = avg_pipeline_duration_sec()
    fields: dict[str, object] = {**snap}
    fields["avg_pipeline_duration_sec"] = round(avg, 4) if avg is not None else None
    log_event(logger, "metrics.pipeline_summary", **fields)


def log_metrics_summary_only(logger: logging.Logger) -> None:
    """Periodic metrics line (same shape as end-of-tick summary)."""
    log_pipeline_metrics(logger)
