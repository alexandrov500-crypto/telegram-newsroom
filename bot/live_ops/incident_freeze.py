from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bot.live_ops.channel_settings import ControlledLiveSettings
from bot.live_ops.repository import LiveChannelRepository


class IncidentFreeze:
    """Publishing freeze and failure cooldown."""

    def __init__(self, settings: ControlledLiveSettings, repository: LiveChannelRepository) -> None:
        self.settings = settings
        self.repository = repository

    def freeze_publishing(self, *, reason: str = "operator") -> None:
        self.repository.update_state(frozen=1, paused=1)
        self.repository.record_incident("freeze", "high", {"reason": reason})
        try:
            from bot.ops_forensics.hooks import record_audit, record_timeline

            record_timeline(
                "freeze_publishing",
                severity="high",
                details={"reason": reason},
            )
            record_audit("freeze_publishing", payload={"reason": reason})
        except Exception:
            pass

    def unfreeze(self) -> None:
        self.repository.update_state(frozen=0)

    def record_failure(self) -> None:
        state = self.repository.get_state() or {}
        failures = int(state.get("failures_recent", 0)) + 1
        updates: dict[str, Any] = {"failures_recent": failures}
        if failures >= self.settings.failure_threshold_pause:
            until = datetime.now(timezone.utc).timestamp() + self.settings.cooldown_after_failures_sec
            updates["cooldown_until"] = datetime.fromtimestamp(until, tz=timezone.utc).isoformat()
            updates["paused"] = 1
            self.repository.record_incident(
                "failure_cooldown",
                "warning",
                {"failures": failures},
            )
        self.repository.update_state(**updates)

    def record_success(self) -> None:
        self.repository.update_state(failures_recent=0, cooldown_until=None)

    def is_in_cooldown(self, state: dict[str, Any]) -> bool:
        until = state.get("cooldown_until")
        if not until:
            return False
        try:
            end = datetime.fromisoformat(str(until).replace("Z", "+00:00"))
            return datetime.now(timezone.utc) < end
        except ValueError:
            return False

    def is_frozen(self) -> bool:
        state = self.repository.get_state() or {}
        return bool(state.get("frozen"))
