from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bot.week1.repository import Week1Repository


@dataclass
class Week1ExecutiveReporting:
    repository: Week1Repository

    def week1_report(self, signals: dict[str, Any]) -> str:
        surv = self.repository.survivability_history(limit=1)
        surv_score = float(surv[0]["survivability_score"]) if surv else 0.0
        return (
            "<b>Week-1 executive report</b>\n\n"
            f"Audience health: {signals.get('audience_health', 0):.2f}\n"
            f"Publication stability: {signals.get('publish_health', 0):.2f}\n"
            f"Operator workload: {signals.get('operator_attention', 0):.2f}\n"
            f"Incidents (open): {signals.get('open_incidents', 0)}\n"
            f"Rollback ready: {'yes' if signals.get('rollback_ready') else 'review'}\n"
            f"Trust: {signals.get('trust_trajectory', 'stable')}\n"
            f"Quality trend: {signals.get('quality_drift', 'stable')}\n"
            f"Scaling pressure: {signals.get('scaling_pressure', 0):.2f}\n"
            f"Survivability: {surv_score:.2f}\n"
            f"Launch confidence: {signals.get('launch_confidence', surv_score):.2f}"
        )

    def launch_confidence(self, signals: dict[str, Any]) -> str:
        base = float(signals.get("go_live_confidence", 0.8))
        risk = float(signals.get("stabilization_risk", 0.3))
        conf = max(0.0, min(1.0, base * (1.0 - risk * 0.4)))
        signals["launch_confidence"] = conf
        level = "strong" if conf > 0.8 else "moderate" if conf > 0.65 else "fragile"
        return f"<b>Launch confidence</b> {conf:.2f} ({level})"
