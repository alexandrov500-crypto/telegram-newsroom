from __future__ import annotations

import os
from typing import Any


def minimal_durable_profile() -> dict[str, Any]:
    """
    What is actually required for 8–15 posts/day supervised pilot — advisory map.
    """
    profile = os.getenv("RUNTIME_PROFILE", "minimal_pilot")
    return {
        "profile_name": profile,
        "mandatory": [
            "ingestion (rss/telethon)",
            "clustering + summarization",
            "publish_guard + canary",
            "trust/hallucination blockers",
            "publish_flow_health funnel",
            "cadence floor (bounded)",
            "operator_digest",
        ],
        "optional_advisory": [
            "vitality_governance",
            "realism_index",
            "baseline_governance",
            "signal_compression",
            "surge/responsiveness modulation",
            "long-tail nudges",
        ],
        "degradable": [
            "recovery_digest",
            "advanced telemetry panels",
            "weekly_self_audit",
            "heuristic_influence_detail",
        ],
        "research_only": [
            "ops_evidence_review",
            "trust_calibration_reports",
            "full consolidation snapshots",
        ],
        "pilot_target_posts_per_day": "8-15",
    }
