from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bot.ops_evolution.repository import OpsEvolutionRepository

_DIMENSIONS = (
    "reliability",
    "governance",
    "scalability",
    "operational",
    "observability",
    "recovery",
    "quality",
    "autonomy",
)


@dataclass
class PlatformMaturityModel:
    repository: OpsEvolutionRepository

    def score(self, signals: dict[str, Any]) -> dict[str, float]:
        scores = {
            "reliability": min(1.0, float(signals.get("uptime_score", 0.9))),
            "governance": min(1.0, float(signals.get("trust_score", 0.85))),
            "scalability": 1.0 - min(1.0, float(signals.get("scaling_risk", 0.2))),
            "operational": min(1.0, float(signals.get("ga_score", 0.8))),
            "observability": 0.85,
            "recovery": min(1.0, float(signals.get("recovery_ok", 1.0))),
            "quality": min(1.0, float(signals.get("quality_avg", 0.8))),
            "autonomy": min(1.0, float(signals.get("autonomy_score", 0.8))),
        }
        overall = sum(scores.values()) / len(scores)
        self.repository.save_maturity_snapshot(scores, overall)
        return {**scores, "overall": overall}

    def status_text(self, signals: dict[str, Any]) -> str:
        s = self.score(signals)
        overall = s.pop("overall", 0)
        weakest = min(s.items(), key=lambda x: x[1])
        lines = [
            f"<b>Maturity</b> overall <b>{overall:.0%}</b>",
            f"Weakest: {weakest[0]} {weakest[1]:.0%}",
        ]
        for dim in _DIMENSIONS[:5]:
            v = s.get(dim, 0)
            bar = "█" * int(v * 5) + "░" * (5 - int(v * 5))
            lines.append(f"{dim[:6]:6} {bar} {v:.0%}")
        return "\n".join(lines)

    def trends_text(self) -> str:
        hist = self.repository.maturity_history(limit=8)
        if not hist:
            return "No maturity snapshots yet."
        lines = ["<b>Maturity trends</b>"]
        for h in hist[:5]:
            lines.append(f"• {h['created_at'][:16]}: {h['overall_score']:.0%}")
        if len(hist) >= 2:
            delta = hist[0]["overall_score"] - hist[-1]["overall_score"]
            lines.append(f"Δ {delta:+.2f} (recent vs oldest shown)")
        return "\n".join(lines)
