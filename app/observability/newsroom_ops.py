"""Newsroom operational dashboard metrics (publish SLA, desk, sources)."""

from __future__ import annotations

from typing import Any

from app.observability.editorial_metrics import editorial_ranking_snapshot
from utils.metrics import export_snapshot


def launch_dashboard(*, runtime_dir: str | None = None) -> dict[str, Any]:
    """Final pre-launch newsroom dashboard."""
    base = newsroom_ops_snapshot(runtime_dir=runtime_dir)
    try:
        from app.editorial.feedback_loop import feedback_summary
        from app.editorial.soft_launch import is_soft_launch_mode, soft_launch_thresholds
        from app.editorial.source_intelligence import top_sources
        from app.observability.newsroom_anomaly import detect_newsroom_anomalies

        base["soft_launch"] = {
            "enabled": is_soft_launch_mode(),
            "thresholds": soft_launch_thresholds().to_dict(),
        }
        base["feedback"] = feedback_summary(runtime_dir=runtime_dir)
        base["top_sources"] = top_sources(runtime_dir=runtime_dir)
        base["anomalies"] = detect_newsroom_anomalies(runtime_dir=runtime_dir)
    except Exception:
        pass
    return base


def newsroom_ops_snapshot(*, runtime_dir: str | None = None) -> dict[str, Any]:
    """Aggregate metrics for /ops.json and staging validators."""
    snap = export_snapshot()
    counters = snap.get("counters") or {}
    histograms = snap.get("histograms") or {}

    publish_lat = histograms.get("publish_latency_ms") or {}
    breaking_lat = histograms.get("breaking_published_latency_ms") or {}

    manual_review = int(counters.get("manual_review_required_total", 0))
    auto_publish = int(counters.get("auto_publish_eligible_total", 0))

    return {
        "publish_frequency": {
            "published_total": int(counters.get("published_total", 0)),
            "publish_success_total": int(counters.get("publish_success_total", 0)),
            "publish_failed_total": int(counters.get("publish_failed_total", 0)),
        },
        "approval_ratio": {
            "drafts_approved_total": int(counters.get("drafts_approved_total", 0)),
            "drafts_rejected_total": int(counters.get("drafts_rejected_total", 0)),
        },
        "desk": {
            "gate": editorial_ranking_snapshot(),
        },
        "publish_latency_ms": {
            "p50": publish_lat.get("p50"),
            "p95": publish_lat.get("p95"),
            "sla_threshold_ms": _publish_sla_ms(),
        },
        "breaking_latency_ms": {
            "p50": breaking_lat.get("p50"),
        },
        "failed_drafts": int(counters.get("failed_draft_recovery_total", 0)),
        "governance_blocks": int(counters.get("governance_block_total", 0)),
        "queue_health": {
            "lane_breaking_depth": int(counters.get("lane_queue_breaking_depth", 0)),
            "lane_high_depth": int(counters.get("lane_queue_high_depth", 0)),
        },
        "editorial_trust": {
            "manual_review_total": manual_review,
            "auto_publish_eligible_total": auto_publish,
            "manual_review_ratio": round(
                manual_review / max(1, manual_review + auto_publish),
                4,
            ),
        },
    }


def _publish_sla_ms() -> int:
    import os

    try:
        return max(60_000, int(os.getenv("NEWSROOM_PUBLISH_SLA_MS", "300000")))
    except ValueError:
        return 300_000


def record_publish_latency_ms(ms: float, *, breaking: bool = False) -> None:
    from utils.metrics import observe_histogram

    observe_histogram("publish_latency_ms", max(0.0, ms) / 1000.0)
    if breaking:
        from app.observability.editorial_metrics import record_breaking_published_latency_ms

        record_breaking_published_latency_ms(ms)
