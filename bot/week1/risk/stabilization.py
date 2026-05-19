from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bot.week1.repository import Week1Repository


@dataclass
class RiskStabilization:
    repository: Week1Repository

    def score(self, signals: dict[str, Any]) -> dict[str, float]:
        quality = float(signals.get("quality_avg", 0.8))
        trust_vol = float(signals.get("trust_volatility", 0.05))
        queue = int(signals.get("queue_depth", 0))
        incidents = int(signals.get("open_incidents", 0))
        worker_ok = float(signals.get("worker_health", 0.9))
        cognition_lat = float(signals.get("cognition_latency_ms", 0)) / 5000.0

        stab_risk = 0.0
        if quality < 0.7:
            stab_risk += 0.25
        if trust_vol > 0.12:
            stab_risk += 0.2
        if queue > 200:
            stab_risk += 0.15
        stab_risk += incidents * 0.08
        stab_risk += (1.0 - worker_ok) * 0.2
        stab_risk += min(cognition_lat, 0.2)
        stab_risk = min(1.0, stab_risk)

        rollback_p = min(
            1.0,
            stab_risk * 0.7
            + (0.15 if signals.get("quality_decay") else 0)
            + (0.1 if trust_vol > 0.15 else 0),
        )
        return {
            "stabilization_risk": round(stab_risk, 4),
            "rollback_probability": round(rollback_p, 4),
        }

    def stabilization_html(self, signals: dict[str, Any]) -> str:
        s = self.score(signals)
        level = "low" if s["stabilization_risk"] < 0.35 else "medium" if s["stabilization_risk"] < 0.6 else "high"
        return f"<b>Stabilization risk</b> {s['stabilization_risk']:.2f} ({level})"

    def rollback_probability_html(self, signals: dict[str, Any]) -> str:
        s = self.score(signals)
        return f"<b>Rollback probability</b> {s['rollback_probability']:.0%}"
