from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bot.post_ga.repository import PostGaRepository


@dataclass
class LiveRiskPredictor:
    """Predict overload, SLO breach, spend spikes, quality collapse."""

    repository: PostGaRepository
    horizon_hours: float = 6.0

    def forecast(
        self,
        *,
        queue_depth: int = 0,
        queue_growth: float = 0.0,
        slo_burn: float = 0.0,
        operator_attention: float = 1.0,
        floodwait_recent: int = 0,
        spend_hour: float = 0.0,
        spend_cap: float = 10.0,
        quality_confidence: float = 0.85,
        trust_score: float = 0.85,
    ) -> dict[str, Any]:
        overload_prob = min(1.0, queue_depth / 600.0 + max(0, queue_growth) / 300.0)
        slo_prob = min(1.0, slo_burn)
        fatigue_prob = min(1.0, 1.0 - operator_attention)
        flood_prob = min(1.0, floodwait_recent / 5.0)
        spend_prob = min(1.0, spend_hour / max(spend_cap, 0.01))
        trust_prob = min(1.0, max(0, 0.9 - trust_score) * 2)
        quality_prob = min(1.0, max(0, 0.7 - quality_confidence) * 2)

        detail = {
            "overload": round(overload_prob, 3),
            "slo_violation": round(slo_prob, 3),
            "operator_fatigue": round(fatigue_prob, 3),
            "telegram_flood": round(flood_prob, 3),
            "ai_spend_spike": round(spend_prob, 3),
            "trust_degradation": round(trust_prob, 3),
            "quality_collapse": round(quality_prob, 3),
        }
        self.repository.save_risk_forecast(
            horizon_hours=self.horizon_hours,
            overload_prob=overload_prob,
            slo_prob=slo_prob,
            detail=detail,
        )
        top = max(detail.items(), key=lambda x: x[1])
        return {
            "horizon_hours": self.horizon_hours,
            "top_risk": top[0],
            "top_probability": top[1],
            "risks": detail,
            "confidence_adjusted": round(1.0 - top[1] * trust_score, 3),
        }

    def forecast_text(self) -> str:
        row = self.repository.latest_risk_forecast()
        if not row:
            return "No forecast yet — wait for ops tick."
        d = row.get("detail", {})
        lines = ["<b>Risk forecast</b> (6h)"]
        for k, v in sorted(d.items(), key=lambda x: -x[1])[:5]:
            mark = "🔴" if v > 0.6 else "🟡" if v > 0.35 else "🟢"
            lines.append(f"{mark} {k}: {v:.0%}")
        return "\n".join(lines)

    def future_pressure_text(self, forecast: dict[str, Any]) -> str:
        return (
            f"<b>Future pressure</b>\n"
            f"Top: {forecast.get('top_risk')} {forecast.get('top_probability', 0):.0%}\n"
            f"Adjusted confidence {forecast.get('confidence_adjusted', 0):.0%}"
        )
