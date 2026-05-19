from __future__ import annotations

from dataclasses import dataclass

from bot.cognitive.repository import CognitiveRepository
from bot.cognitive.types import Prediction


@dataclass
class OperationalSignals:
    queue_backlog: int = 0
    stream_lag_sec: float = 0.0
    dlq_count: int = 0
    replay_backlog: int = 0
    digest_pending: int = 0
    publish_rate_per_min: float = 0.0
    federation_lag_sec: float = 0.0
    node_cpu_pressure: float = 0.0


class PredictiveOperationsEngine:
    """Explainable operational forecasting with confidence scores."""

    def __init__(self, repository: CognitiveRepository) -> None:
        self._repo = repository
        self._history: list[OperationalSignals] = []

    def observe(self, signals: OperationalSignals) -> None:
        self._history.append(signals)
        if len(self._history) > 48:
            self._history = self._history[-48:]

    def forecast(self, signals: OperationalSignals) -> list[Prediction]:
        predictions: list[Prediction] = []
        backlog_growth = self._trend(lambda s: float(s.queue_backlog))
        if backlog_growth > 5:
            predictions.append(
                Prediction(
                    "backlog_growth",
                    60,
                    min(1.0, signals.queue_backlog / 500),
                    0.7 + min(0.2, backlog_growth / 100),
                    f"backlog rising ({signals.queue_backlog}, trend +{backlog_growth:.1f}/tick)",
                )
            )
        if signals.stream_lag_sec > 30:
            predictions.append(
                Prediction(
                    "replay_storm",
                    30,
                    min(1.0, signals.stream_lag_sec / 120),
                    0.75,
                    f"stream lag {signals.stream_lag_sec:.0f}s may trigger replay pressure",
                )
            )
        if signals.digest_pending > 3 and signals.queue_backlog > 100:
            predictions.append(
                Prediction(
                    "digest_spike",
                    45,
                    0.8,
                    0.65,
                    "digest queue + editorial backlog correlate",
                )
            )
        if signals.dlq_count > 50:
            predictions.append(
                Prediction(
                    "federation_instability",
                    90,
                    min(1.0, signals.dlq_count / 200),
                    0.6,
                    f"DLQ depth {signals.dlq_count} suggests transport degradation",
                )
            )
        if signals.publish_rate_per_min > 8:
            predictions.append(
                Prediction(
                    "publish_surge",
                    15,
                    min(1.0, signals.publish_rate_per_min / 15),
                    0.8,
                    f"publish rate {signals.publish_rate_per_min:.1f}/min",
                )
            )
        for p in predictions:
            self._repo.save_forecast(p)
            try:
                from bot.observability.metrics import record_prediction

                record_prediction(p.forecast_type)
            except Exception:
                pass
        return predictions

    def preemptive_actions(self, predictions: list[Prediction]) -> list[str]:
        actions: list[str] = []
        for p in predictions:
            if p.forecast_type == "replay_storm" and p.confidence > 0.7:
                actions.append("slow_replay_rate")
            if p.forecast_type == "digest_spike" and p.confidence > 0.6:
                actions.append("preemptive_digest_lease")
            if p.forecast_type == "publish_surge" and p.confidence > 0.75:
                actions.append("throttle_analytics")
            if p.forecast_type == "federation_instability" and p.confidence > 0.55:
                actions.append("suspend_federation_sync")
        return actions

    def _trend(self, accessor) -> float:
        if len(self._history) < 2:
            return 0.0
        return accessor(self._history[-1]) - accessor(self._history[-2])
