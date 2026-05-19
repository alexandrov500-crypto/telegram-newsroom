from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class PlatformGovernance:
    """Ecosystem risk, plugin trust, accountability chains."""

    def ecosystem_risk_score(
        self,
        *,
        plugin_trust_avg: float,
        policy_drift_count: int,
        quarantined_plugins: int,
        open_incidents: int,
    ) -> float:
        risk = 0.0
        risk += (1.0 - plugin_trust_avg) * 0.3
        risk += min(policy_drift_count * 0.1, 0.3)
        risk += min(quarantined_plugins * 0.15, 0.3)
        risk += min(open_incidents * 0.05, 0.2)
        return min(risk, 1.0)

    def ecosystem_risk_text(self, score: float, details: dict[str, Any]) -> str:
        level = "low" if score < 0.3 else "medium" if score < 0.6 else "high"
        return (
            f"<b>Ecosystem risk</b> {score:.2f} ({level})\n"
            f"Plugin trust avg: {details.get('trust_avg', 0):.2f}\n"
            f"Drift issues: {details.get('drift', 0)}\n"
            f"Quarantined: {details.get('quarantined', 0)}"
        )

    def governance_audit_text(self, plugins: list[dict[str, Any]], policies: int) -> str:
        low_trust = [p for p in plugins if float(p.get("trust_score", 1)) < 0.7]
        lines = [
            "<b>Governance audit</b>",
            f"Policies registered: {policies}",
            f"Plugins reviewed: {len(plugins)}",
            f"Low trust plugins: {len(low_trust)}",
        ]
        for p in low_trust[:3]:
            lines.append(f"⚠ {p['name']} trust {p['trust_score']:.2f}")
        return "\n".join(lines)
