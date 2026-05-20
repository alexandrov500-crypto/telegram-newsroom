"""Production runtime counters (Prometheus via utils.metrics)."""
from __future__ import annotations

from utils.metrics import export_snapshot, inc

POLLING_RESTARTS = "polling_restarts_total"
TELEGRAM_CONFLICTS = "telegram_conflicts_total"
TELEGRAM_NETWORK_FAILURES = "telegram_network_failures_total"
OPENAI_FAILURES_TOTAL = "openai_failures_total"
DEGRADED_TRANSITIONS = "degraded_state_transitions_total"


def inc_polling_restart(delta: int = 1) -> None:
    inc(POLLING_RESTARTS, delta)


def inc_telegram_conflict(delta: int = 1) -> None:
    inc(TELEGRAM_CONFLICTS, delta)


def inc_telegram_network_failure(delta: int = 1) -> None:
    inc(TELEGRAM_NETWORK_FAILURES, delta)


def inc_openai_failure_total(delta: int = 1) -> None:
    inc(OPENAI_FAILURES_TOTAL, delta)
    inc("openai_failures", delta)


def inc_degraded_transition(delta: int = 1) -> None:
    inc(DEGRADED_TRANSITIONS, delta)


def export_merged_metrics() -> dict:
    snap = export_snapshot()
    ctr = snap.setdefault("counters", {})
    for key in (
        POLLING_RESTARTS,
        TELEGRAM_CONFLICTS,
        TELEGRAM_NETWORK_FAILURES,
        OPENAI_FAILURES_TOTAL,
        DEGRADED_TRANSITIONS,
        "scored_articles_total",
        "scoring_failures_total",
    ):
        ctr.setdefault(key, 0)
    g = snap.setdefault("gauges", {})
    g.setdefault("average_quality_score", 0.0)
    g.setdefault("average_novelty_score", 0.0)
    return snap
