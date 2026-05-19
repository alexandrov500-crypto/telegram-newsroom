from __future__ import annotations

from typing import Any

IMMUTABLE_CORE = "IMMUTABLE_CORE"
STABLE_OPERATIONAL = "STABLE_OPERATIONAL"
CONTROLLED_EXPERIMENTAL = "CONTROLLED_EXPERIMENTAL"
ACTIVE_EXPERIMENTAL = "ACTIVE_EXPERIMENTAL"

TIERS = (
    IMMUTABLE_CORE,
    STABLE_OPERATIONAL,
    CONTROLLED_EXPERIMENTAL,
    ACTIVE_EXPERIMENTAL,
)

_SUBSYSTEM_TIERS: dict[str, str] = {
    "publish_guard": IMMUTABLE_CORE,
    "publish_flow": IMMUTABLE_CORE,
    "trust_gates": IMMUTABLE_CORE,
    "anti_flood": IMMUTABLE_CORE,
    "resilience": IMMUTABLE_CORE,
    "misinformation_blockers": IMMUTABLE_CORE,
    "hallucination_guards": IMMUTABLE_CORE,
    "clustering_engine": IMMUTABLE_CORE,
    "ingestion": IMMUTABLE_CORE,
    "rehearsal": STABLE_OPERATIONAL,
    "certification": STABLE_OPERATIONAL,
    "slimming": STABLE_OPERATIONAL,
    "reliability": STABLE_OPERATIONAL,
    "cadence_tuning": STABLE_OPERATIONAL,
    "relaxation_governance": STABLE_OPERATIONAL,
    "vitality_governance": STABLE_OPERATIONAL,
    "degradation_modes": STABLE_OPERATIONAL,
    "digest_compression": STABLE_OPERATIONAL,
    "digest_wording": CONTROLLED_EXPERIMENTAL,
    "clustering_heuristics": CONTROLLED_EXPERIMENTAL,
    "canary_balance": CONTROLLED_EXPERIMENTAL,
    "trust_calibration": CONTROLLED_EXPERIMENTAL,
    "vitality_telemetry": CONTROLLED_EXPERIMENTAL,
    "ai_enrichment": ACTIVE_EXPERIMENTAL,
    "editorial_intelligence": ACTIVE_EXPERIMENTAL,
    "future_scoring": ACTIVE_EXPERIMENTAL,
}


def classify_subsystem(name: str) -> str:
    return _SUBSYSTEM_TIERS.get(name, STABLE_OPERATIONAL)


def tier_summary(registry: dict[str, dict[str, Any]]) -> dict[str, int]:
    counts = {t: 0 for t in TIERS}
    for meta in registry.values():
        tier = str(meta.get("tier", STABLE_OPERATIONAL))
        if tier in counts:
            counts[tier] += 1
    return counts
