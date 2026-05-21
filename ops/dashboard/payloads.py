"""Compact dashboard JSON payloads (cache-friendly, stable schema)."""

from __future__ import annotations

import time
from typing import Any


async def dashboard_overview(settings: Any) -> dict[str, Any]:
    from ops.runtime_api import (
        list_recent_incidents,
        runtime_circuit_payload,
        runtime_status_payload,
        runtime_watchdog_payload,
    )

    status = await runtime_status_payload(settings)
    watchdog = await runtime_watchdog_payload()
    circuit = runtime_circuit_payload()
    return {
        "schema_version": 1,
        "generated_at_unix": time.time(),
        "status": status,
        "watchdog": watchdog,
        "openai_circuit": circuit,
        "incidents_recent": list_recent_incidents(settings, limit=5),
    }


async def dashboard_editorial(settings: Any) -> dict[str, Any]:
    from editorial.governance.diversity_controls import diversity_metrics
    from editorial.governance.drift import compute_drift_signals
    from editorial.governance.policies_engine import policies_payload
    from editorial.governance.ranking import get_last_ranking_snapshot
    from editorial.governance.reputation import reputation_snapshot

    rd = settings.runtime_state_dir
    return {
        "schema_version": 1,
        "generated_at_unix": time.time(),
        "policies": policies_payload(rd),
        "ranking": get_last_ranking_snapshot(rd),
        "reputation_top": dict(list(reputation_snapshot(rd).get("channels", {}).items())[:12]),
        "diversity": diversity_metrics(rd),
        "drift": compute_drift_signals(rd),
    }


def dashboard_incidents(settings: Any) -> dict[str, Any]:
    from ops.runtime_api import list_recent_incidents

    bundles = list_recent_incidents(settings, limit=20)
    return {
        "schema_version": 1,
        "generated_at_unix": time.time(),
        "count": len(bundles),
        "bundles": bundles,
    }


def dashboard_publication(settings: Any) -> dict[str, Any]:
    from ops.analytics.publication import publication_analytics_payload
    from ops.resilience.publish_journal import journal_tail

    rd = settings.runtime_state_dir
    return {
        "schema_version": 1,
        "generated_at_unix": time.time(),
        "analytics": publication_analytics_payload(rd, days=7),
        "journal_tail": journal_tail(rd, limit=25),
    }
