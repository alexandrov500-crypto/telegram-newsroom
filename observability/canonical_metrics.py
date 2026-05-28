"""Canonical metrics whitelist — avoid metrics explosion (Phase 3 freeze)."""

from __future__ import annotations

# Gauges/counters operators and dashboards may rely on (stable).
CANONICAL_GAUGES: frozenset[str] = frozenset(
    {
        "queue_depth",
        "openai_circuit_open",
        "pipeline_tick_duration_seconds",
        "publish_success_total",
        "publish_failures",
        "drafts_created",
        "failed_draft_retry_pending",
        "stale_pipeline_ticks",
        "maintenance_active",
    }
)

CANONICAL_COUNTERS: frozenset[str] = frozenset(
    {
        "publishes",
        "publish_retries",
        "publish_failures",
        "drafts_created",
        "telegram_conflict_total",
        "openai_failure_total",
    }
)

CANONICAL_HISTOGRAMS: frozenset[str] = frozenset(
    {
        "scheduler_cycle_duration_seconds",
        "publish_duration_seconds",
        "openai_request_duration_seconds",
    }
)

ALL_CANONICAL: frozenset[str] = CANONICAL_GAUGES | CANONICAL_COUNTERS | CANONICAL_HISTOGRAMS


def audit_exported_metrics(snapshot: dict) -> dict[str, list[str]]:
    """Return non-canonical metric names (informational only)."""
    gauges = set((snapshot.get("gauges") or {}).keys())
    counters = set((snapshot.get("counters") or {}).keys())
    hists = set((snapshot.get("histograms") or {}).keys())
    return {
        "non_canonical_gauges": sorted(gauges - CANONICAL_GAUGES)[:40],
        "non_canonical_counters": sorted(counters - CANONICAL_COUNTERS)[:40],
        "non_canonical_histograms": sorted(hists - CANONICAL_HISTOGRAMS)[:40],
    }
