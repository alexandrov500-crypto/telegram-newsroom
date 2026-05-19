from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from bot.reliability.settings import ReliabilitySettings
from bot.reliability.types import HealthState, PublishMode

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PublishGateVerdict:
    allowed: bool
    mode: PublishMode
    reason: str
    blockers: tuple[str, ...] = ()

    def summary(self) -> str:
        status = "ALLOW" if self.allowed else "BLOCK"
        return f"{status} [{self.mode.value}] {self.reason}"


@dataclass
class PublishGateController:
    """Safe transition from shadow to limited/full production publishing."""

    settings: ReliabilitySettings
    _stable_since: float | None = field(default=None, init=False)
    _limited_publishes: list[float] = field(default_factory=list, init=False)
    _mode_override: PublishMode | None = field(default=None, init=False)

    def set_mode(self, mode: PublishMode) -> None:
        self._mode_override = mode
        logger.info("event=publish_mode_set mode=%s", mode.value)

    def current_mode(self) -> PublishMode:
        if self._mode_override is not None:
            return self._mode_override
        return self.settings.resolve_publish_mode()

    def evaluate(
        self,
        *,
        health_state: HealthState,
        health_score: float,
        queue_depth: int,
        cognition_latency_ms: float,
        telegram_failure_rate: float,
        moderation_ok: bool = True,
        telegram_delivery_ok: bool = True,
        fatal_incidents_recent: int = 0,
        operator_approved: bool = False,
    ) -> PublishGateVerdict:
        mode = self.current_mode()
        blockers: list[str] = []

        if mode == PublishMode.DRY_RUN:
            return PublishGateVerdict(False, mode, "dry_run_active")

        if health_state == HealthState.FAILED:
            blockers.append("runtime_failed")
        if fatal_incidents_recent > self.settings.publish_max_fatal_incidents:
            blockers.append(f"fatal_incidents={fatal_incidents_recent}")
        if queue_depth > self.settings.publish_max_queue_depth:
            blockers.append(f"queue_depth={queue_depth}")
        if cognition_latency_ms > self.settings.publish_max_cognition_latency_ms:
            blockers.append(f"cognition_latency_ms={cognition_latency_ms:.0f}")
        if telegram_failure_rate > self.settings.publish_max_telegram_failure_rate:
            blockers.append(f"telegram_failure_rate={telegram_failure_rate:.2f}")
        if not moderation_ok:
            blockers.append("moderation_unhealthy")
        if not telegram_delivery_ok:
            blockers.append("telegram_delivery_unhealthy")

        if health_score >= 0.75 and not blockers:
            if self._stable_since is None:
                self._stable_since = time.monotonic()
        else:
            self._stable_since = None

        stable_sec = 0.0
        if self._stable_since is not None:
            stable_sec = time.monotonic() - self._stable_since

        if mode == PublishMode.SHADOW:
            return PublishGateVerdict(
                allowed=False,
                mode=mode,
                reason="shadow_publish_only",
                blockers=tuple(blockers) if blockers else ("shadow_mode",),
            )

        if stable_sec < self.settings.publish_stability_sec:
            blockers.append(
                f"stability={stable_sec:.0f}s need={self.settings.publish_stability_sec:.0f}s",
            )

        if mode == PublishMode.LIMITED_PRODUCTION:
            self._prune_hourly_publishes()
            if len(self._limited_publishes) >= self.settings.limited_production_cap_per_hour:
                blockers.append("limited_production_cap")
            if blockers:
                return PublishGateVerdict(False, mode, "limited_blocked", tuple(blockers))
            if not operator_approved:
                return PublishGateVerdict(False, mode, "operator_approval_required")
            return PublishGateVerdict(True, mode, "limited_ok")

        if mode == PublishMode.FULL_PRODUCTION:
            if blockers:
                return PublishGateVerdict(False, mode, "full_blocked", tuple(blockers))
            if not operator_approved:
                return PublishGateVerdict(False, mode, "operator_approval_required")
            return PublishGateVerdict(True, mode, "full_ok")

        return PublishGateVerdict(False, mode, "unknown_mode")

    def record_publish(self) -> None:
        if self.current_mode() == PublishMode.LIMITED_PRODUCTION:
            self._limited_publishes.append(time.monotonic())

    def _prune_hourly_publishes(self) -> None:
        cutoff = time.monotonic() - 3600.0
        self._limited_publishes = [t for t in self._limited_publishes if t >= cutoff]
