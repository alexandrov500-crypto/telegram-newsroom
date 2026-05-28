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
    "polling_restarts_total": 0,
    "telegram_conflicts_total": 0,
    "telegram_network_failures_total": 0,
    "openai_failures_total": 0,
    "degraded_state_transitions_total": 0,
    "scored_articles_total": 0,
    "scoring_failures_total": 0,
    "queue_overflow_total": 0,
    "desk_rejected_items_total": 0,
    "desk_included_items_total": 0,
    "desk_breaking_override_count": 0,
    "desk_scoring_total": 0,
    "dropped_items_total": 0,
    "breaking_lane_published_total": 0,
    "high_lane_processed_total": 0,
    "normal_lane_processed_total": 0,
    "breaking_items_total": 0,
    "high_score_items_total": 0,
    "suppressed_duplicates_total": 0,
    "compressed_items_dropped_total": 0,
    "draft_clusters_kept_total": 0,
    "editorial_gate_rejected_total": 0,
    "editorial_gate_passed_total": 0,
    "fast_lane_processed_total": 0,
    "dropped_due_to_overflow_total": 0,
    "routing_decision_fast_total": 0,
    "routing_decision_standard_total": 0,
    "routing_decision_slow_total": 0,
    "ledger_events_total": 0,
    "ledger_ingested_total": 0,
    "ledger_routed_total": 0,
    "ledger_dropped_total": 0,
    "ledger_published_total": 0,
    "ledger_dropped_duplicates_total": 0,
}

_gauges: dict[str, float] = {}

_pipeline_sec_sum = 0.0
_pipeline_sec_count = 0

# Prometheus-style histogram buckets (seconds).
_HISTOGRAM_BUCKET_UPPER = (
    0.01,
    0.05,
    0.1,
    0.25,
    0.5,
    1.0,
    2.5,
    5.0,
    10.0,
    30.0,
    60.0,
    float("inf"),
)
_histograms: dict[str, list[int]] = {}
_histogram_sums: dict[str, float] = {}
_histogram_counts: dict[str, int] = {}

PIPELINE_HISTOGRAMS = (
    "collect_duration_seconds",
    "summarize_duration_seconds",
    "scoring_duration_seconds",
    "publish_duration_seconds",
    "scheduler_cycle_duration_seconds",
    "breaking_latency_seconds",
    "breaking_published_latency_ms",
    "fast_lane_latency_ms",
)


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


def _histogram_bucket_index(value: float) -> int:
    v = max(0.0, float(value))
    for i, upper in enumerate(_HISTOGRAM_BUCKET_UPPER):
        if v <= upper:
            return i
    return len(_HISTOGRAM_BUCKET_UPPER) - 1


def observe_histogram(name: str, value_sec: float) -> None:
    """Record one observation into an in-process histogram (seconds)."""
    if value_sec < 0:
        return
    key = str(name)
    with _lock:
        if key not in _histograms:
            _histograms[key] = [0] * len(_HISTOGRAM_BUCKET_UPPER)
        idx = _histogram_bucket_index(value_sec)
        _histograms[key][idx] += 1
        _histogram_sums[key] = _histogram_sums.get(key, 0.0) + float(value_sec)
        _histogram_counts[key] = _histogram_counts.get(key, 0) + 1


def histogram_snapshot() -> dict[str, dict[str, Any]]:
    with _lock:
        out: dict[str, dict[str, Any]] = {}
        labels = [
            "inf" if b == float("inf") else str(b) for b in _HISTOGRAM_BUCKET_UPPER
        ]
        for name, buckets in _histograms.items():
            out[name] = {
                "buckets": dict(zip(labels, buckets)),
                "sum": round(_histogram_sums.get(name, 0.0), 6),
                "count": int(_histogram_counts.get(name, 0)),
            }
        return out


def reset_metrics() -> None:
    """Reset counters, gauges, and pipeline duration aggregates (tests / admin)."""
    global _pipeline_sec_sum, _pipeline_sec_count
    with _lock:
        for k in list(_counts.keys()):
            _counts[k] = 0
        _gauges.clear()
        _pipeline_sec_sum = 0.0
        _pipeline_sec_count = 0
        _histograms.clear()
        _histogram_sums.clear()
        _histogram_counts.clear()


def export_snapshot() -> dict[str, Any]:
    """JSON-friendly metrics export (counters + gauges + timing aggregates)."""
    with _lock:
        avg = None
        if _pipeline_sec_count > 0:
            avg = _pipeline_sec_sum / _pipeline_sec_count
        return {
            "counters": dict(_counts),
            "gauges": dict(_gauges),
            "histograms": histogram_snapshot(),
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
