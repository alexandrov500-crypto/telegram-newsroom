from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bot.ops_evolution.repository import OpsEvolutionRepository


class LongHorizonAnalytics:
    def __init__(self, repository: OpsEvolutionRepository) -> None:
        self._repo = repository
        self._weekly_buffer: dict[str, float] = {}

    def ingest_tick(self, *, signals: dict[str, Any]) -> None:
        self._weekly_buffer["quality"] = float(signals.get("quality_avg", 0.8))
        self._weekly_buffer["trust"] = float(signals.get("trust_score", 0.85))
        self._weekly_buffer["autonomy"] = float(signals.get("autonomy_score", 0.8))
        self._weekly_buffer["operator_load"] = float(signals.get("operator_attention", 1.0))

    def flush_weekly_if_due(self) -> None:
        key = datetime.now(timezone.utc).strftime("%Y-W%W")
        if not self._weekly_buffer:
            return
        sustainability = sum(self._weekly_buffer.values()) / len(self._weekly_buffer)
        self._repo.save_analytics_period(
            period="weekly",
            period_key=key,
            metrics=dict(self._weekly_buffer),
            sustainability=sustainability,
        )

    def maturity_trajectory(self) -> str:
        hist = self._repo.maturity_history(limit=6)
        if len(hist) < 2:
            return "Insufficient maturity history."
        delta = hist[0]["overall_score"] - hist[-1]["overall_score"]
        trend = "improving" if delta > 0.02 else "declining" if delta < -0.02 else "stable"
        return f"Maturity {trend} (Δ {delta:+.2f} over {len(hist)} snapshots)"
