"""Editorial ranking + suppression metrics."""

from __future__ import annotations

from typing import Any

from utils.metrics import inc, observe_histogram


def record_breaking_item() -> None:
    inc("breaking_items_total")


def record_high_score_item() -> None:
    inc("high_score_items_total")


def record_suppressed_duplicate() -> None:
    inc("suppressed_duplicates_total")


def record_editorial_gate_rejected() -> None:
    inc("editorial_gate_rejected_total")


def record_editorial_gate_passed() -> None:
    inc("editorial_gate_passed_total")


def record_breaking_published_latency_ms(ms: float) -> None:
    observe_histogram("breaking_published_latency_ms", max(0.0, ms) / 1000.0)


def editorial_ranking_snapshot() -> dict[str, Any]:
    from utils.metrics import export_snapshot

    c = export_snapshot().get("counters") or {}
    h = export_snapshot().get("histograms") or {}
    lat = h.get("breaking_published_latency_ms") or h.get("breaking_latency_seconds") or {}
    return {
        "breaking_items_total": int(c.get("breaking_items_total", 0)),
        "high_score_items_total": int(c.get("high_score_items_total", 0)),
        "suppressed_duplicates_total": int(c.get("suppressed_duplicates_total", 0)),
        "compressed_items_dropped_total": int(c.get("compressed_items_dropped_total", 0)),
        "draft_clusters_kept_total": int(c.get("draft_clusters_kept_total", 0)),
        "editorial_gate_rejected_total": int(c.get("editorial_gate_rejected_total", 0)),
        "editorial_gate_passed_total": int(c.get("editorial_gate_passed_total", 0)),
        "breaking_published_latency_ms_p50": lat.get("p50"),
    }
