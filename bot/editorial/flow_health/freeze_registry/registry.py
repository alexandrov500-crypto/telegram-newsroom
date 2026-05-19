from __future__ import annotations

from typing import Any

from bot.editorial.flow_health.freeze_registry.classifier import (
    ACTIVE_EXPERIMENTAL,
    CONTROLLED_EXPERIMENTAL,
    IMMUTABLE_CORE,
    STABLE_OPERATIONAL,
    TIERS,
    classify_subsystem,
    tier_summary,
)


def build_freeze_registry() -> dict[str, Any]:
    """Operational surface stability map — advisory classification only."""
    entries: dict[str, dict[str, Any]] = {}
    for name in (
        "publish_guard",
        "publish_flow",
        "trust_gates",
        "anti_flood",
        "resilience",
        "misinformation_blockers",
        "hallucination_guards",
        "clustering_engine",
        "ingestion",
        "rehearsal",
        "certification",
        "slimming",
        "reliability",
        "cadence_tuning",
        "relaxation_governance",
        "vitality_governance",
        "degradation_modes",
        "digest_compression",
        "digest_wording",
        "clustering_heuristics",
        "canary_balance",
        "trust_calibration",
        "vitality_telemetry",
        "ai_enrichment",
        "editorial_intelligence",
        "future_scoring",
    ):
        tier = classify_subsystem(name)
        entries[name] = {
            "tier": tier,
            "mutable": tier not in (IMMUTABLE_CORE,),
            "advisory_only": True,
        }

    summary = tier_summary(entries)
    experimental_ratio = round(
        (summary.get(CONTROLLED_EXPERIMENTAL, 0) + summary.get(ACTIVE_EXPERIMENTAL, 0))
        / max(1, len(entries)),
        3,
    )

    return {
        "registry": entries,
        "tier_counts": summary,
        "experimental_surface_ratio": experimental_ratio,
        "immutable_core": [n for n, m in entries.items() if m["tier"] == IMMUTABLE_CORE],
        "stable_operational": [n for n, m in entries.items() if m["tier"] == STABLE_OPERATIONAL],
        "controlled_experimental": [
            n for n, m in entries.items() if m["tier"] == CONTROLLED_EXPERIMENTAL
        ],
        "active_experimental": [n for n, m in entries.items() if m["tier"] == ACTIVE_EXPERIMENTAL],
        "tiers": list(TIERS),
    }
