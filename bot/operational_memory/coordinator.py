from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from bot.operational_memory.drift.monitor import DriftMonitor
from bot.operational_memory.fingerprints.engine import FingerprintEngine
from bot.operational_memory.learning.outcomes import OutcomeLearner
from bot.operational_memory.memory_store.incidents import IncidentMemoryStore
from bot.operational_memory.prediction.engine import PredictiveRiskEngine
from bot.operational_memory.recommendations.v2 import OperationalRecommendationsV2
from bot.operational_memory.repository import OperationalMemoryRepository
from bot.operational_memory.seasonality.calendar import SeasonalityCalendar
from bot.operational_memory.settings import OperationalMemorySettings


class OperationalMemoryCoordinator:
    def __init__(
        self,
        *,
        settings: OperationalMemorySettings,
        repository: OperationalMemoryRepository,
        incidents: IncidentMemoryStore,
        fingerprints: FingerprintEngine,
        prediction: PredictiveRiskEngine,
        drift: DriftMonitor,
        seasonality: SeasonalityCalendar,
        recommendations: OperationalRecommendationsV2,
        outcomes: OutcomeLearner,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.incidents = incidents
        self.fingerprints = fingerprints
        self.prediction = prediction
        self.drift = drift
        self.seasonality = seasonality
        self.recommendations = recommendations
        self.outcomes = outcomes
        self._signals: dict[str, Any] = {}
        self._signals_fn: Callable[[], dict[str, Any]] | None = None
        self._tick_count = 0
        self._last_prune = 0.0

    def configure_signals(self, fn: Callable[[], dict[str, Any]]) -> None:
        self._signals_fn = fn

    async def startup(self) -> None:
        self.repository.ensure_state(retention_days=self.settings.retention_days)

    async def tick(self, *, signals: dict[str, Any] | None = None) -> dict[str, Any]:
        if signals is not None:
            sig = dict(signals)
        elif self._signals_fn is not None:
            sig = dict(self._signals_fn())
        else:
            sig = dict(self._signals)
        self._signals = sig
        sig.setdefault("queue_spike_threshold", self.settings.queue_spike_threshold)
        sig.setdefault("retry_storm_threshold", self.settings.retry_storm_threshold)
        self._tick_count += 1

        opened: list[str] = []
        if self.settings.auto_incident_capture:
            opened = self.incidents.detect_from_signals(sig)
            for inc in opened:
                self.fingerprints.register_from_incident(
                    incident_type=inc["incident_type"],
                    signals=sig,
                    impact=float(sig.get("stabilization_risk", 0.3)),
                    recovery_sec=None,
                )

        season_profile: dict[str, Any] = {}
        if self.settings.seasonality_enabled:
            season_profile = self.seasonality.update(sig)
            sig["seasonal_baseline"] = self.seasonality.contextual_baseline(sig)

        drift_state: dict[str, dict[str, Any]] = {}
        if self.settings.drift_enabled:
            drift_state = self.drift.evaluate(sig)

        predictions: dict[str, dict[str, Any]] = {}
        if self.settings.prediction_enabled:
            predictions = self.prediction.forecast_all(sig)

        proposals: list[dict[str, Any]] = []
        if predictions:
            proposals = self.recommendations.generate(
                signals=sig,
                predictions=predictions,
                drift=drift_state,
            )

        if self._tick_count % 48 == 0:
            self._maybe_prune()

        return {
            "incidents_opened": len(opened),
            "predictions": {h: predictions[h].get("degradation") for h in predictions},
            "drift_domains": len(drift_state),
            "proposals": len(proposals),
            "season_bucket": season_profile.get("bucket"),
        }

    def _maybe_prune(self) -> None:
        now = time.time()
        if now - self._last_prune < 3600:
            return
        self.repository.prune_retention(days=self.settings.retention_days)
        self._last_prune = now

    def snapshot(self) -> dict[str, Any]:
        return {
            "enabled": self.settings.enabled,
            "tick_count": self._tick_count,
            "incidents_recent": len(self.repository.list_incidents(limit=5)),
            "fingerprints": len(self.repository.list_fingerprints(limit=5)),
            "predictions": self.repository.latest_predictions(),
            "drift": self.repository.latest_drift(),
        }

    def incident_history_html(self, *, limit: int = 10) -> str:
        rows = self.repository.list_incidents(limit=limit)
        lines = ["<b>Incident history</b>"]
        for r in rows:
            lines.append(
                f"• {r['incident_type']} [{r['severity']}] {r['started_at'][:16]}",
            )
        if len(lines) == 1:
            lines.append("No incidents recorded.")
        return "\n".join(lines)

    def recurrent_failures_html(self) -> str:
        rows = self.repository.recurrent_types(min_count=2)
        lines = ["<b>Recurrent failures</b>"]
        for r in rows:
            lines.append(f"• {r['incident_type']}: {r['count']}× avg surv {r['avg_survivability']:.0%}")
        if len(lines) == 1:
            lines.append("No recurring patterns yet (need ≥2 same type).")
        return "\n".join(lines)

    def operational_memory_html(self) -> str:
        snap = self.snapshot()
        return (
            "<b>Operational memory</b>\n"
            f"Ticks: {snap['tick_count']} · recent incidents: {snap['incidents_recent']}\n"
            f"Fingerprints tracked: {snap['fingerprints']}\n"
            "Predictive layer active — advisory only."
        )
