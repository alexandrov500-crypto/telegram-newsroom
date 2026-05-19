from __future__ import annotations

from typing import Any

from bot.live_ops.channel_settings import ControlledLiveSettings
from bot.live_ops.repository import LiveChannelRepository


class AnomalyHold:
    """Auto-pause after anomaly spike; reduce effective publish rate."""

    def __init__(self, settings: ControlledLiveSettings, repository: LiveChannelRepository) -> None:
        self.settings = settings
        self.repository = repository
        self._anomaly_window: list[bool] = []

    def observe_failure(self, *, failed: bool) -> None:
        self._anomaly_window.append(failed)
        if len(self._anomaly_window) > 20:
            self._anomaly_window = self._anomaly_window[-20:]

    def check_spike(self) -> bool:
        if len(self._anomaly_window) < self.settings.anomaly_spike_threshold:
            return False
        recent = self._anomaly_window[-self.settings.anomaly_spike_threshold :]
        return sum(recent) >= self.settings.anomaly_spike_threshold

    def apply_hold_if_needed(self) -> dict[str, Any] | None:
        if not self.settings.freeze_on_anomaly:
            return None
        if not self.check_spike():
            return None
        self.repository.update_state(paused=1, frozen=1)
        self.repository.record_incident(
            "anomaly_spike",
            "critical",
            {"window_failures": self.settings.anomaly_spike_threshold},
        )
        return {"paused": True, "frozen": True, "reason": "anomaly_spike"}
