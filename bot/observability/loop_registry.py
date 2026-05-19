from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class LoopHeartbeat:
    name: str
    interval_sec: float
    last_tick_monotonic: float = field(default_factory=time.monotonic)
    last_duration_sec: float = 0.0
    tick_count: int = 0
    last_error: str | None = None
    recovery_count: int = 0

    def record_tick(self, duration_sec: float, *, error: str | None = None) -> None:
        self.last_tick_monotonic = time.monotonic()
        self.last_duration_sec = duration_sec
        self.tick_count += 1
        self.last_error = error

    def age_sec(self) -> float:
        return time.monotonic() - self.last_tick_monotonic

    def is_stalled(self, *, multiplier: float = 3.0) -> bool:
        threshold = max(self.interval_sec * multiplier, self.interval_sec + 120.0)
        return self.age_sec() > threshold


class LoopHeartbeatRegistry:
    """Tracks background loop health for long-running operation."""

    def __init__(self) -> None:
        self._loops: dict[str, LoopHeartbeat] = {}
        self._watchdog_eligible: frozenset[str] = frozenset()
        self._profile_configured = False

    def reset(self) -> None:
        self._loops.clear()
        self._watchdog_eligible = frozenset()
        self._profile_configured = False

    def configure_from_profile(self, caps: Any) -> None:
        """Reset and register only loops enabled for the runtime profile."""
        from bot.runtime.loop_manifest import (
            loop_registration_manifest,
            loops_eligible_for_watchdog,
        )
        from bot.runtime.profile import loop_enabled

        self.reset()
        for name, mode, interval in loop_registration_manifest(caps):
            if loop_enabled(mode):
                self._loops[name] = LoopHeartbeat(name=name, interval_sec=interval)
        self._watchdog_eligible = loops_eligible_for_watchdog(caps)
        self._profile_configured = True
        logger.info(
            "event=loop_registry_configured profile=%s monitored=%s",
            caps.profile.value,
            sorted(self._watchdog_eligible),
        )

    def register(self, name: str, interval_sec: float) -> None:
        if self._profile_configured and name not in self._watchdog_eligible:
            return
        self._loops[name] = LoopHeartbeat(name=name, interval_sec=interval_sec)

    def heartbeat(self, name: str, duration_sec: float, *, error: str | None = None) -> None:
        loop = self._loops.get(name)
        if loop is None:
            return
        loop.record_tick(duration_sec, error=error)
        try:
            from bot.observability.metrics import observe_runtime_loop_latency

            observe_runtime_loop_latency(name, duration_sec)
        except Exception:
            pass

    def stalled_loops(self) -> list[LoopHeartbeat]:
        return [
            lb
            for lb in self._loops.values()
            if lb.name in self._watchdog_eligible and lb.is_stalled()
        ]

    def watchdog_stalled_names(self, *, caps: Any | None = None) -> list[str]:
        """Stalled loops that pass profile + optional live-task validation."""
        from bot.runtime.profile import filter_watchdog_stalled_names

        raw = [lb.name for lb in self.stalled_loops()]
        return filter_watchdog_stalled_names(raw, caps=caps, registry=self)

    def snapshot(self) -> dict[str, Any]:
        return {
            name: {
                "age_sec": round(lb.age_sec(), 1),
                "interval_sec": lb.interval_sec,
                "ticks": lb.tick_count,
                "last_duration_sec": round(lb.last_duration_sec, 3),
                "stalled": lb.is_stalled(),
                "watchdog_eligible": name in self._watchdog_eligible,
                "last_error": lb.last_error,
                "recoveries": lb.recovery_count,
            }
            for name, lb in self._loops.items()
        }

    def runtime_loops_view(self, caps: Any | None = None) -> dict[str, Any]:
        from bot.runtime.loop_manifest import runtime_loops_classification
        from bot.runtime.profile import get_runtime_capabilities

        c = caps or get_runtime_capabilities()
        classified = runtime_loops_classification(c)
        registered = sorted(self._loops.keys())
        return {
            "runtime_profile": c.profile.value,
            "active": classified["active"],
            "passive": classified["passive"],
            "disabled": classified["disabled"],
            "watchdog_monitored": sorted(self._watchdog_eligible),
            "registered": registered,
        }

    def mark_recovery(self, name: str) -> None:
        if name in self._loops:
            self._loops[name].recovery_count += 1

    @property
    def profile_configured(self) -> bool:
        return self._profile_configured


_registry: LoopHeartbeatRegistry | None = None


def get_loop_registry() -> LoopHeartbeatRegistry:
    global _registry
    if _registry is None:
        _registry = LoopHeartbeatRegistry()
    return _registry


def reset_and_configure_loop_registry(caps: Any) -> LoopHeartbeatRegistry:
    """Fresh registry bound to the current runtime profile (call once at startup)."""
    global _registry
    reg = LoopHeartbeatRegistry()
    reg.configure_from_profile(caps)
    _registry = reg
    return reg


def loop_task_is_running(name: str) -> bool:
    try:
        current = asyncio.current_task()
        for task in asyncio.all_tasks():
            if task is current or task.done():
                continue
            if task.get_name() == name:
                return True
    except RuntimeError:
        pass
    return False
