from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any

_lock = threading.RLock()
_mod_lat: deque[float] = deque(maxlen=256)
_publish_attempts_ring: deque[int] = deque(maxlen=128)


def reset_editorial_analytics_for_tests() -> None:
    """Clear in-process rings (unit tests / soak isolation)."""
    with _lock:
        _mod_lat.clear()
        _publish_attempts_ring.clear()


def record_moderation_publish_latency_sec(sec: float) -> None:
    if sec <= 0 or sec > 864000:
        return
    with _lock:
        _mod_lat.append(float(sec))


def record_publish_attempt_count(attempts: int) -> None:
    if attempts < 0:
        return
    with _lock:
        _publish_attempts_ring.append(int(attempts))


def export_editorial_analytics(metrics_snapshot: dict[str, int]) -> dict[str, Any]:
    """Lightweight in-process editorial stats (no DB)."""
    with _lock:
        lat = list(_mod_lat)
        att = list(_publish_attempts_ring)
    avg_lat = round(sum(lat) / len(lat), 2) if lat else None
    avg_attempts = round(sum(att) / len(att), 2) if att else None
    dc = int(metrics_snapshot.get("drafts_created", 0) or 0)
    pub = int(metrics_snapshot.get("publishes", 0) or 0)
    rej = int(metrics_snapshot.get("drafts_rejected", 0) or 0)
    skips = int(metrics_snapshot.get("skipped_duplicates", 0) or 0)
    pf = int(metrics_snapshot.get("publish_failures", 0) or 0)
    denom = max(1, pub + pf)
    success_rate = round(pub / denom, 4)
    mod_denom = max(1, pub + rej)
    rejection_rate = round(rej / mod_denom, 4)
    dup_denom = max(1, dc + skips)
    duplicate_skip_rate = round(skips / dup_denom, 4)
    ctr = dict(metrics_snapshot)
    supp = int(ctr.get("skipped_intelligence_suppress", 0) or 0)
    defer = int(ctr.get("cadence_deferred_cluster", 0) or 0)
    clus = int(ctr.get("clusters_created", 0) or 0)
    cbp = int(ctr.get("cadence_blocked_publish", 0) or 0)
    edits = int(ctr.get("draft_edits", 0) or 0)
    ai_calls = int(ctr.get("ai_cluster_calls", 0) or 0)
    ai_fail = int(ctr.get("ai_cluster_failures", 0) or 0) + int(ctr.get("openai_failures", 0) or 0)
    oai_retry = int(ctr.get("openai_retries", 0) or 0)
    intel_suppress_ratio = round(supp / max(1, clus), 4) if clus else None
    cadence_defer_ratio = round(defer / max(1, clus), 4) if clus else None
    cadence_block_pressure = round(cbp / max(1, pub + cbp), 4) if (pub + cbp) else None
    ai_failure_ratio = round(ai_fail / max(1, ai_calls), 4) if ai_calls else None
    edits_per_publish = round(edits / max(1, pub), 4) if pub else None
    return {
        "moderation_latency_avg_sec": avg_lat,
        "moderation_latency_samples": len(lat),
        "avg_publish_attempts_ring": avg_attempts,
        "publish_success_rate": success_rate,
        "rejection_rate": rejection_rate,
        "duplicate_skip_rate": duplicate_skip_rate,
        "drafts_created_counter": dc,
        "publishes_counter": pub,
        "drafts_rejected_counter": rej,
        "skipped_duplicates_counter": skips,
        "publish_failures_counter": pf,
        "intelligence_suppress_ratio_vs_clusters": intel_suppress_ratio,
        "cadence_defer_ratio_vs_clusters": cadence_defer_ratio,
        "cadence_blocked_publish_pressure": cadence_block_pressure,
        "ai_failure_ratio_vs_cluster_calls": ai_failure_ratio,
        "openai_retries_counter": oai_retry,
        "draft_edits_counter": edits,
        "editorial_edits_per_publish": edits_per_publish,
    }
