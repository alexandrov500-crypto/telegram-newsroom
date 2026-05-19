from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bot.week1.repository import Week1Repository


@dataclass
class SurvivabilityScoring:
    repository: Week1Repository

    def compute(self, signals: dict[str, Any]) -> dict[str, float]:
        uptime = float(signals.get("uptime_score", 0.95))
        queue_stab = 1.0 - min(int(signals.get("queue_depth", 0)) / 300.0, 1.0)
        incidents = int(signals.get("open_incidents", 0))
        recovery = float(signals.get("recovery_ok", 0.9))
        operator = 1.0 - float(signals.get("operator_attention", 0.5))
        rollback = 1.0 if signals.get("rollback_ready") else 0.5
        quality = float(signals.get("quality_avg", 0.8))

        score = (
            uptime * 0.2
            + queue_stab * 0.15
            + (1.0 - min(incidents * 0.15, 0.6)) * 0.15
            + recovery * 0.15
            + operator * 0.1
            + rollback * 0.1
            + quality * 0.15
        )
        score = max(0.0, min(1.0, score))

        hist = self.repository.survivability_history(limit=3)
        trend = score
        if hist:
            trend = (score + float(hist[0]["survivability_score"])) / 2.0

        detail = {
            "uptime": uptime,
            "queue_stability": queue_stab,
            "incidents": incidents,
            "recovery": recovery,
        }
        self.repository.save_survivability(
            score=score,
            confidence_trend=trend,
            detail=detail,
        )
        return {"survivability_score": round(score, 4), "confidence_trend": round(trend, 4)}

    def survivability_html(self) -> str:
        hist = self.repository.survivability_history(limit=1)
        if not hist:
            return "<b>Survivability</b> Insufficient data."
        s = float(hist[0]["survivability_score"])
        level = "strong" if s > 0.8 else "moderate" if s > 0.65 else "at risk"
        return f"<b>Survivability</b> {s:.2f} ({level})"

    def confidence_trend_html(self) -> str:
        hist = self.repository.survivability_history(limit=5)
        if len(hist) < 2:
            return "<b>Confidence trend</b> Building history…"
        vals = [float(h["confidence_trend"]) for h in reversed(hist)]
        delta = vals[-1] - vals[0]
        direction = "↑" if delta > 0.02 else "↓" if delta < -0.02 else "→"
        return f"<b>Confidence trend</b> {vals[-1]:.2f} {direction} (Δ{delta:+.2f})"
