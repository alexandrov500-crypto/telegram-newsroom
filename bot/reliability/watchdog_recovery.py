from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from bot.reliability.settings import ReliabilitySettings
from bot.reliability.types import HealthState, SubsystemName

logger = logging.getLogger(__name__)

RecoveryHook = Callable[[str, dict[str, Any]], Awaitable[None]]


@dataclass
class RecoveryAttempt:
    subsystem: str
    action: str
    attempt: int
    success: bool
    detail: str
    at_monotonic: float = field(default_factory=time.monotonic)


class SubsystemWatchdog:
    """Detect stalls and attempt bounded recovery with exponential backoff."""

    def __init__(
        self,
        settings: ReliabilitySettings,
        *,
        on_incident: Callable[..., Any] | None = None,
    ) -> None:
        self._settings = settings
        self._on_incident = on_incident
        self._attempts: dict[str, int] = {}
        self._next_retry: dict[str, float] = {}
        self._history: list[RecoveryAttempt] = []
        self._hooks: dict[str, RecoveryHook] = {}

    def register_recovery_hook(self, subsystem: str, hook: RecoveryHook) -> None:
        self._hooks[subsystem] = hook

    def _backoff_sec(self, subsystem: str) -> float:
        n = self._attempts.get(subsystem, 0)
        delay = min(
            self._settings.recovery_backoff_max_sec,
            self._settings.recovery_backoff_base_sec * (2**n),
        )
        return delay

    async def evaluate(
        self,
        *,
        stalled_loops: list[str],
        queue_backlog: int,
        health_state: HealthState,
        telegram_failures: int = 0,
        openai_timeouts: int = 0,
    ) -> list[RecoveryAttempt]:
        results: list[RecoveryAttempt] = []
        now = time.monotonic()

        triggers: list[tuple[str, str, str]] = []
        if stalled_loops:
            for loop in stalled_loops:
                triggers.append((f"loop:{loop}", "ingest" if "ingest" in loop else "scheduler", loop))
        if queue_backlog > self._settings.publish_max_queue_depth:
            triggers.append(("publish_queue", "publish", "queue_stall"))
        if telegram_failures >= 5:
            triggers.append(("telegram_api", SubsystemName.TELEGRAM_API.value, "api_failures"))
        if openai_timeouts >= 5:
            triggers.append(("openai_api", SubsystemName.OPENAI_API.value, "timeout_spike"))
        if health_state in (HealthState.CRITICAL, HealthState.FAILED):
            triggers.append(("runtime", "scheduler", health_state.value))

        for key, subsystem, action in triggers:
            if now < self._next_retry.get(key, 0):
                continue
            attempt = self._attempts.get(key, 0) + 1
            if attempt > self._settings.recovery_max_attempts:
                if self._on_incident:
                    await self._on_incident(
                        title=f"Recovery exhausted: {key}",
                        severity="CRITICAL",
                        subsystem=subsystem,
                        detail=f"action={action} attempts={attempt}",
                        correlation_key=f"recovery:{key}",
                    )
                continue

            self._attempts[key] = attempt
            self._next_retry[key] = now + self._backoff_sec(key)
            success = False
            detail = "hook_missing"
            hook = self._hooks.get(subsystem) or self._hooks.get(key.split(":")[0])
            ctx = {"action": action, "attempt": attempt, "stalled_loops": stalled_loops}
            if hook is not None:
                try:
                    await hook(action, ctx)
                    success = True
                    detail = "hook_ok"
                except Exception as exc:
                    detail = str(exc)[:200]
                    logger.exception("event=recovery_hook_failed key=%s", key)
            else:
                # Default: yield scheduler
                import asyncio

                await asyncio.sleep(0)
                success = True
                detail = "scheduler_yield"

            rec = RecoveryAttempt(
                subsystem=subsystem,
                action=action,
                attempt=attempt,
                success=success,
                detail=detail,
            )
            self._history.append(rec)
            results.append(rec)
            logger.info(
                "event=recovery_attempt subsystem=%s action=%s attempt=%d success=%s",
                subsystem,
                action,
                attempt,
                success,
            )
            if not success and self._on_incident:
                await self._on_incident(
                    title=f"Recovery failed: {action}",
                    severity="ERROR",
                    subsystem=subsystem,
                    detail=detail,
                    correlation_key=f"recovery:{key}",
                    recovery_status=f"attempt_{attempt}_failed",
                )

        return results

    def recent_attempts(self, limit: int = 10) -> list[RecoveryAttempt]:
        return self._history[-limit:]
