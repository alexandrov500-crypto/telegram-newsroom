from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ResilienceContext:
    """In-process load-shedding flags — read by publish, analytics, lifecycle."""

    posture: str = "stable"
    reduce_publish_attempts: float = 1.0
    ingestion_throttle_multiplier: float = 1.0
    defer_non_critical_writes: bool = False
    pause_background_analytics: bool = False
    suspend_archival: bool = False
    observation_only: bool = False
    active_actions: list[str] = field(default_factory=list)
    last_updated: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "posture": self.posture,
            "reduce_publish_attempts": self.reduce_publish_attempts,
            "ingestion_throttle_multiplier": self.ingestion_throttle_multiplier,
            "defer_non_critical_writes": self.defer_non_critical_writes,
            "pause_background_analytics": self.pause_background_analytics,
            "suspend_archival": self.suspend_archival,
            "observation_only": self.observation_only,
            "active_actions": list(self.active_actions),
            "last_updated": self.last_updated,
        }


_context = ResilienceContext()


def get_resilience_context() -> ResilienceContext:
    return _context


def should_defer_analytics() -> bool:
    ctx = _context
    return ctx.pause_background_analytics or ctx.defer_non_critical_writes


def should_suspend_archival() -> bool:
    return _context.suspend_archival


def publish_attempt_multiplier() -> float:
    return max(0.0, min(1.0, _context.reduce_publish_attempts))


def is_observation_only() -> bool:
    return _context.observation_only
