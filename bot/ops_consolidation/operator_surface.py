from __future__ import annotations

from typing import Any

from bot.ops_consolidation.types import CommandTier


OPERATOR_COMMANDS: list[dict[str, Any]] = [
    {"command": "/operator_digest", "tier": CommandTier.PRIMARY, "purpose": "Daily operational snapshot"},
    {"command": "/resilience_status", "tier": CommandTier.PRIMARY, "purpose": "Posture, budgets, guidance"},
    {"command": "/weekly_review", "tier": CommandTier.PRIMARY, "purpose": "Evidence-based weekly review"},
    {"command": "/live_dashboard", "tier": CommandTier.PRIMARY, "purpose": "Live canary dashboard"},
    {"command": "/pause_live", "tier": CommandTier.PRIMARY, "purpose": "Emergency pause"},
    {"command": "/resume_live", "tier": CommandTier.PRIMARY, "purpose": "Resume publishing"},
    {"command": "/trust_calibration", "tier": CommandTier.REFERENCE, "purpose": "Subsystem trust bands"},
    {"command": "/attention_queue", "tier": CommandTier.REFERENCE, "purpose": "Batched alerts"},
    {"command": "/priority_queue", "tier": CommandTier.REFERENCE, "purpose": "Editorial ranking"},
    {"command": "/preview_post", "tier": CommandTier.REFERENCE, "purpose": "Pre-publish editorial check"},
    {"command": "/ops_storage", "tier": CommandTier.REFERENCE, "purpose": "Storage and retention"},
    {"command": "/storyline", "tier": CommandTier.DIAGNOSTIC, "purpose": "Narrative thread detail"},
    {"command": "/publish_trace", "tier": CommandTier.DIAGNOSTIC, "purpose": "Single publish forensics"},
    {"command": "/live_status", "tier": CommandTier.DIAGNOSTIC, "purpose": "Raw live state"},
    {"command": "/canary_status", "tier": CommandTier.DEPRECATED_ALIAS, "purpose": "Use /live_status"},
    {"command": "/channel_health", "tier": CommandTier.DIAGNOSTIC, "purpose": "Channel trust metrics"},
    {"command": "/runtime_identity", "tier": CommandTier.DIAGNOSTIC, "purpose": "Process identity"},
    {"command": "/pilot_preflight", "tier": CommandTier.DIAGNOSTIC, "purpose": "Startup checks"},
]


def operator_surface_audit() -> dict[str, Any]:
    by_tier: dict[str, list[str]] = {}
    for cmd in OPERATOR_COMMANDS:
        tier = cmd["tier"].value if hasattr(cmd["tier"], "value") else str(cmd["tier"])
        by_tier.setdefault(tier, []).append(cmd["command"])

    return {
        "commands": OPERATOR_COMMANDS,
        "by_tier": by_tier,
        "primary_workflow": [
            "1. /operator_digest — daily health",
            "2. /resilience_status — if degraded or incidents",
            "3. /weekly_review — weekly tuning (Mondays)",
            "4. /live_dashboard — during active publishing",
        ],
        "simplification_notes": [
            "Prefer digest over separate /live_status + /channel_health during routine ops",
            "Use /publish_trace only for single-post debugging",
            "Trust and evidence layers are reference, not daily drivers",
        ],
        "total_commands": len(OPERATOR_COMMANDS),
        "primary_count": len(by_tier.get(CommandTier.PRIMARY.value, [])),
    }
