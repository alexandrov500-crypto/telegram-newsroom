from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class LaunchDashboardBuilder:
    """Executive mobile-first launch dashboard."""

    def build(
        self,
        *,
        certification_state: str = "NOT_READY",
        certification_score: float = 0.0,
        rollout_stage: str = "INTERNAL_SHADOW",
        risk_score: float = 0.0,
        slo_violations: int = 0,
        publish_health: float = 1.0,
        telegram_health: float = 1.0,
        ai_spend_usd: float = 0.0,
        trust_score: float = 0.85,
        active_incidents: int = 0,
        rollback_ready: bool = True,
        confidence_trend: float = 0.0,
        activation_stage: str = "PRECHECK",
        rc_lockdown: bool = False,
    ) -> str:
        cert_emoji = {
            "CERTIFIED": "✅",
            "CONDITIONAL": "🟡",
            "NOT_READY": "⛔",
            "LOCKED_DOWN": "🔒",
        }.get(certification_state, "⚪")
        risk_emoji = "🟢" if risk_score < 0.3 else "🟡" if risk_score < 0.6 else "🔴"
        lines = [
            "<b>🚀 Launch dashboard</b>",
            f"{cert_emoji} Cert <b>{certification_state}</b> {certification_score:.0%}",
            f"Stage <code>{activation_stage}</code> · Rollout <code>{rollout_stage}</code>",
            f"{risk_emoji} Risk {risk_score:.0%} · Conf {confidence_trend:.0%}",
            f"Pub {publish_health:.0%} · TG {telegram_health:.0%} · Trust {trust_score:.2f}",
            f"SLO Δ {slo_violations} · Inc {active_incidents} · ${ai_spend_usd:.2f}/d",
            f"Rollback: {'ready' if rollback_ready else 'busy'} · Lockdown: {'on' if rc_lockdown else 'off'}",
        ]
        if certification_state != "CERTIFIED":
            lines.append("<i>→ /certification_status then /go_live_certify</i>")
        elif activation_stage != "GENERAL_AVAILABILITY":
            lines.append("<i>→ /activation_status · /activate_next_stage</i>")
        return "\n".join(lines)
