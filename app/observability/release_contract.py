"""Single source of truth for release validation contract."""

from __future__ import annotations

from enum import Enum


class FinalVerdict(str, Enum):
    NOT_READY = "NOT_READY"
    CONDITIONAL = "CONDITIONAL"
    READY_FOR_PUBLIC = "READY_FOR_PUBLIC"


REQUIRED_CONTRACT_FIELDS: set[str] = {
    "execution_graph_verdict",
    "publish_finalize_order_valid",
    "no_critical_runtime_events",
    "no_duplicate_publish_detected",
    "rollback_state_stable",
}

OBSERVATIONAL_CONTRACT_FIELDS: set[str] = {
    "publish_continuity_score",
    "telegram_health",
    "traffic_metrics",
    "latency_metrics",
    "engagement_proxy",
}

