from __future__ import annotations

from typing import Any

# Static maintenance map — aligned with ops_consolidation contracts.
_SUBSYSTEM_RISK: dict[str, dict[str, Any]] = {
    "publish_guard": {"risk": "HIGH", "criticality": "runtime"},
    "publish_flow": {"risk": "HIGH", "criticality": "runtime"},
    "clustering": {"risk": "HIGH", "criticality": "runtime"},
    "ingestion": {"risk": "HIGH", "criticality": "runtime"},
    "canary_mode": {"risk": "HIGH", "criticality": "runtime"},
    "flow_health_floor": {"risk": "MODERATE", "criticality": "adaptive"},
    "relaxation_budget": {"risk": "MODERATE", "criticality": "adaptive"},
    "vitality_telemetry": {"risk": "LOW", "criticality": "advisory"},
    "signal_compression": {"risk": "LOW", "criticality": "advisory"},
    "baseline_governance": {"risk": "LOW", "criticality": "advisory"},
    "durability_modes": {"risk": "LOW", "criticality": "advisory"},
    "operator_digest": {"risk": "LOW", "criticality": "telemetry"},
}


def analyze_change_risk(
    *,
    influence_count: int = 0,
) -> dict[str, Any]:
    summary = sorted(
        [{"subsystem": k, **v} for k, v in _SUBSYSTEM_RISK.items()],
        key=lambda x: {"HIGH": 0, "MODERATE": 1, "LOW": 2}.get(str(x["risk"]), 3),
    )
    high = [s["subsystem"] for s in summary if s["risk"] == "HIGH"]
    coupling_penalty = min(0.2, max(0, influence_count - 4) * 0.03)
    avg_risk = 0.35 + coupling_penalty
    return {
        "change_risk_by_subsystem": summary,
        "high_risk_subsystems": high,
        "change_risk_summary_score": round(min(1.0, avg_risk), 3),
        "safest_to_modify": [s["subsystem"] for s in summary if s["risk"] == "LOW"][:5],
    }
