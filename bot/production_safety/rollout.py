from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from bot.production_safety.repository import ProductionSafetyRepository
from bot.production_safety.settings import ProductionSafetySettings
from bot.production_safety.types import RolloutStage

logger = logging.getLogger(__name__)

_STAGE_LIMITS: dict[RolloutStage, dict[str, float | int]] = {
    RolloutStage.INTERNAL_SHADOW: {
        "publishes_per_hour": 0,
        "auto_approval": 0,
        "token_budget_multiplier": 0.5,
    },
    RolloutStage.LIMITED_CHANNELS: {
        "publishes_per_hour": 6,
        "auto_approval": 0,
        "token_budget_multiplier": 0.7,
    },
    RolloutStage.LOW_FREQUENCY_PUBLIC: {
        "publishes_per_hour": 12,
        "auto_approval": 0,
        "token_budget_multiplier": 0.85,
    },
    RolloutStage.NORMAL_PRODUCTION: {
        "publishes_per_hour": 40,
        "auto_approval": 0,
        "token_budget_multiplier": 1.0,
    },
    RolloutStage.HIGH_VOLUME_PRODUCTION: {
        "publishes_per_hour": 120,
        "auto_approval": 0,
        "token_budget_multiplier": 1.0,
    },
}


@dataclass
class RolloutController:
    """Phased production rollout with instant shadow rollback."""

    settings: ProductionSafetySettings
    repository: ProductionSafetyRepository
    _publish_timestamps: list[float] = field(default_factory=list)

    def current_stage(self) -> RolloutStage:
        raw = self.repository.get_rollout_stage()
        try:
            return RolloutStage(raw)
        except ValueError:
            try:
                return RolloutStage(self.settings.rollout_stage)
            except ValueError:
                return RolloutStage.INTERNAL_SHADOW

    def set_stage(self, stage: RolloutStage, *, reason: str = "operator") -> RolloutStage:
        prev = self.current_stage()
        self.repository.set_rollout_stage(
            stage.value,
            previous=prev.value,
            detail={"reason": reason},
        )
        logger.info("event=rollout_stage_change from=%s to=%s reason=%s", prev.value, stage.value, reason)
        return stage

    def rollback_to_shadow(self, *, reason: str) -> RolloutStage:
        prev = self.current_stage()
        self.repository.set_rollout_stage(
            RolloutStage.INTERNAL_SHADOW.value,
            previous=prev.value,
            detail={"reason": reason, "auto": True},
            increment_rollback=True,
        )
        logger.critical("event=rollout_rollback from=%s reason=%s", prev.value, reason)
        return RolloutStage.INTERNAL_SHADOW

    def channel_allowed(self, channel_id: int) -> bool:
        stage = self.current_stage()
        if stage == RolloutStage.INTERNAL_SHADOW:
            return False
        if self.settings.channel_whitelist and channel_id not in self.settings.channel_whitelist:
            return False
        return True

    def record_publish(self) -> None:
        self._publish_timestamps.append(time.monotonic())
        self._prune()

    def publishes_remaining_hour(self) -> int:
        self._prune()
        limits = _STAGE_LIMITS.get(self.current_stage(), {})
        cap = int(limits.get("publishes_per_hour", 0))
        return max(0, cap - len(self._publish_timestamps))

    def can_publish_now(self) -> tuple[bool, str]:
        stage = self.current_stage()
        if stage == RolloutStage.INTERNAL_SHADOW:
            return False, "rollout_internal_shadow"
        self._prune()
        limits = _STAGE_LIMITS.get(stage, {})
        cap = int(limits.get("publishes_per_hour", 0))
        if cap > 0 and len(self._publish_timestamps) >= cap:
            return False, f"rollout_rate_cap_{cap}_per_hour"
        return True, "ok"

    def limits(self) -> dict[str, float | int]:
        return dict(_STAGE_LIMITS.get(self.current_stage(), {}))

    def _prune(self) -> None:
        cutoff = time.monotonic() - 3600.0
        self._publish_timestamps = [t for t in self._publish_timestamps if t >= cutoff]
