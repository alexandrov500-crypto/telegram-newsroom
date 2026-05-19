from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bot.ga_ops.readiness.evaluator import GaReadinessResult


@dataclass
class ProductionSummaryBuilder:
    def build(
        self,
        *,
        ga: GaReadinessResult,
        publish_health: float = 1.0,
        operational_risk: float = 0.0,
        quality_trend: float = 0.0,
        ai_spend_usd: float = 0.0,
        rollback_ready: bool = True,
        scaling_risk: float = 0.0,
        active_incidents: int = 0,
        certification_state: str = "NOT_READY",
        traffic_pressure: str = "PUBLIC_TRAFFIC_SAFE",
        audience_signal: str = "stable",
    ) -> str:
        risk_e = "🟢" if operational_risk < 0.3 else "🟡" if operational_risk < 0.6 else "🔴"
        lines = [
            "<b>📡 Production summary</b>",
            f"GA {ga.state.value} {ga.score:.0%} · Cert {certification_state}",
            f"Pub {publish_health:.0%} · Quality {quality_trend:.2f} · ${ai_spend_usd:.2f}",
            f"{risk_e} Risk {operational_risk:.0%} · Scale {scaling_risk:.0%}",
            f"Traffic {traffic_pressure} · Audience {audience_signal}",
            f"Inc {active_incidents} · Rollback {'ok' if rollback_ready else 'busy'}",
        ]
        if ga.state != ga.state.GA_READY:
            lines.append("<i>→ /ga_evaluate · /launch_dashboard</i>")
        return "\n".join(lines)
