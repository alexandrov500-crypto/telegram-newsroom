from __future__ import annotations

from typing import Any

from bot.ops_consolidation.types import TelemetryTier


TELEMETRY_REGISTRY: list[dict[str, Any]] = [
    {"stream": "observation_pulse", "tier": TelemetryTier.CRITICAL, "surface": "/observation_pulse, digest"},
    {"stream": "resilience_posture", "tier": TelemetryTier.CRITICAL, "surface": "/ops_resilience, /resilience_status"},
    {"stream": "live_status", "tier": TelemetryTier.CRITICAL, "surface": "/live_status, /live_dashboard"},
    {"stream": "operator_digest", "tier": TelemetryTier.CRITICAL, "surface": "/operator_digest"},
    {"stream": "publish_funnel", "tier": TelemetryTier.OPERATIONAL, "surface": "operator_digest funnel block"},
    {"stream": "trust_calibration", "tier": TelemetryTier.OPERATIONAL, "surface": "/trust_calibration"},
    {"stream": "weekly_review", "tier": TelemetryTier.OPERATIONAL, "surface": "/weekly_review"},
    {"stream": "priority_queue", "tier": TelemetryTier.OPERATIONAL, "surface": "/priority_queue"},
    {"stream": "attention_queue", "tier": TelemetryTier.OPERATIONAL, "surface": "/attention_queue"},
    {"stream": "ops_storage", "tier": TelemetryTier.OPERATIONAL, "surface": "/ops_storage"},
    {"stream": "incident_timeline", "tier": TelemetryTier.FORENSIC, "surface": "/incident_timeline"},
    {"stream": "operational_audit", "tier": TelemetryTier.FORENSIC, "surface": "/operational_audit"},
    {"stream": "publish_trace", "tier": TelemetryTier.FORENSIC, "surface": "/publish_trace"},
    {"stream": "platform", "tier": TelemetryTier.DEBUG, "surface": "/platform"},
    {"stream": "certification", "tier": TelemetryTier.DEBUG, "surface": "/certification"},
    {"stream": "evolution", "tier": TelemetryTier.DEBUG, "surface": "/evolution"},
    {"stream": "post_ga", "tier": TelemetryTier.DEBUG, "surface": "/post_ga"},
]


def telemetry_tiering_report() -> dict[str, Any]:
    by_tier: dict[str, list[str]] = {t.value: [] for t in TelemetryTier}
    for row in TELEMETRY_REGISTRY:
        by_tier[row["tier"].value].append(row["stream"])
    return {
        "registry": TELEMETRY_REGISTRY,
        "by_tier": by_tier,
        "operator_visible_count": len(by_tier[TelemetryTier.CRITICAL.value])
        + len(by_tier[TelemetryTier.OPERATIONAL.value]),
        "discipline_rules": [
            "critical: max 4 surfaces in daily operator workflow",
            "operational: on-demand only",
            "forensic: never push to Telegram by default",
            "debug: disabled unless APP_ENV=development",
        ],
    }
