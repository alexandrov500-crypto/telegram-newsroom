from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class LiveExecutiveTelemetry:
    def build(
        self,
        *,
        audience: float,
        publish_efficiency: float,
        autonomy_score: float,
        risk_top: str,
        risk_prob: float,
        quality_confidence: float,
        trust_trend: str,
        operator_attention: float,
        scaling_risk: float,
        ga_confidence: float,
        rollback_ready: bool = True,
    ) -> str:
        stab = "🟢" if autonomy_score >= 0.8 else "🟡" if autonomy_score >= 0.6 else "🔴"
        lines = [
            "<b>📡 Live exec</b>",
            f"Audience {audience:.0%} · Pub eff {publish_efficiency:.0%}",
            f"{stab} Stability {autonomy_score:.0%} · GA conf {ga_confidence:.0%}",
            f"Quality {quality_confidence:.2f} · Trust {trust_trend}",
            f"Risk {risk_top} {risk_prob:.0%} · Scale {scaling_risk:.0%}",
            f"Ops attention {operator_attention:.0%} · Rollback {'ok' if rollback_ready else 'busy'}",
        ]
        return "\n".join(lines)
