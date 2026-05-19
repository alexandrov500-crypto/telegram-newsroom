from __future__ import annotations

from typing import Any

from bot.operational_memory.repository import OperationalMemoryRepository


_HORIZONS = ("15m", "1h", "6h", "24h")
_HORIZON_WEIGHT = {"15m": 1.0, "1h": 0.85, "6h": 0.65, "24h": 0.45}


class PredictiveRiskEngine:
    """Explainable rolling-window risk forecasts — no ML."""

    def __init__(self, repository: OperationalMemoryRepository) -> None:
        self.repository = repository
        self._history: list[dict[str, float]] = []

    def observe(self, signals: dict[str, Any]) -> None:
        self._history.append(
            {
                "queue": float(signals.get("queue_depth", 0)),
                "risk": float(signals.get("stabilization_risk", 0.3)),
                "surv": float(signals.get("survivability_score", 0.8)),
                "conf": float(signals.get("confidence_trend", 0.8)),
                "fatigue": float(signals.get("publish_fatigue", 0.2)),
            },
        )
        if len(self._history) > 96:
            self._history = self._history[-96:]

    def forecast_all(self, signals: dict[str, Any]) -> dict[str, dict[str, Any]]:
        self.observe(signals)
        out: dict[str, dict[str, Any]] = {}
        recurrent = self.repository.recurrent_types(min_count=2)
        rec_boost = min(0.2, len(recurrent) * 0.05)

        for h in _HORIZONS:
            w = _HORIZON_WEIGHT[h]
            base_risk = float(signals.get("stabilization_risk", 0.3))
            slope = self._confidence_slope()
            queue_trend = self._queue_trend()
            degradation = min(1.0, (base_risk + rec_boost + max(0, -slope) * 0.3) * w)
            rollback = min(
                1.0,
                float(signals.get("rollback_probability", 0.1)) * w + rec_boost,
            )
            queue_overflow = min(1.0, (queue_trend / 300.0 + base_risk * 0.4) * w)
            alert_storm = min(
                1.0,
                float(signals.get("noise_index", 0.3)) * 0.5 * w + rec_boost * 0.5,
            )
            audience_fatigue = min(
                1.0,
                float(signals.get("publish_fatigue", signals.get("audience_fatigue", 0.2)))
                * w
                + max(0, -slope) * 0.2,
            )
            explain = {
                "base_risk": base_risk,
                "confidence_slope": slope,
                "queue_trend": queue_trend,
                "recurrent_boost": rec_boost,
                "horizon_weight": w,
            }
            self.repository.save_prediction(
                horizon=h,
                degradation=degradation,
                rollback=rollback,
                queue_overflow=queue_overflow,
                alert_storm=alert_storm,
                audience_fatigue=audience_fatigue,
                explain=explain,
            )
            out[h] = {
                "degradation": degradation,
                "rollback": rollback,
                "queue_overflow": queue_overflow,
                "alert_storm": alert_storm,
                "audience_fatigue": audience_fatigue,
                "explain": explain,
            }
        return out

    def _confidence_slope(self) -> float:
        if len(self._history) < 4:
            return 0.0
        recent = [h["conf"] for h in self._history[-4:]]
        return (recent[-1] - recent[0]) / max(len(recent) - 1, 1)

    def _queue_trend(self) -> float:
        if len(self._history) < 3:
            return float(self._history[-1]["queue"]) if self._history else 0.0
        return self._history[-1]["queue"] - self._history[-3]["queue"]

    def predictive_risk_html(self) -> str:
        preds = self.repository.latest_predictions()
        lines = ["<b>Predictive risk</b> (explainable)"]
        for h in _HORIZONS:
            p = preds.get(h, {})
            if not p:
                continue
            lines.append(
                f"<b>{h}</b> deg {p.get('risk_degradation', 0):.0%} · "
                f"rollback {p.get('risk_rollback', 0):.0%} · "
                f"queue {p.get('risk_queue_overflow', 0):.0%}",
            )
        if len(lines) == 1:
            lines.append("No forecasts yet — waiting for ops ticks.")
        return "\n".join(lines)

    def risk_forecast_html(self) -> str:
        preds = self.repository.latest_predictions()
        p24 = preds.get("24h", {})
        return (
            "<b>Risk forecast (24h)</b>\n"
            f"Degradation: {p24.get('risk_degradation', 0):.0%}\n"
            f"Rollback: {p24.get('risk_rollback', 0):.0%}\n"
            f"Queue overflow: {p24.get('risk_queue_overflow', 0):.0%}"
        )
