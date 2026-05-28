"""Soft launch mode — stricter thresholds before public go-live."""

from __future__ import annotations

import os
from dataclasses import dataclass


def is_soft_launch_mode() -> bool:
    return os.getenv("SOFT_LAUNCH_MODE", "false").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class SoftLaunchThresholds:
    min_signal_score: float
    auto_publish_signal_min: float
    min_trust_score: float
    force_manual_review: bool
    max_publishes_per_hour_hint: int

    def to_dict(self) -> dict[str, object]:
        return {
            "min_signal_score": self.min_signal_score,
            "auto_publish_signal_min": self.auto_publish_signal_min,
            "min_trust_score": self.min_trust_score,
            "force_manual_review": self.force_manual_review,
            "max_publishes_per_hour_hint": self.max_publishes_per_hour_hint,
        }


def soft_launch_thresholds() -> SoftLaunchThresholds:
    if not is_soft_launch_mode():
        return SoftLaunchThresholds(
            min_signal_score=_f("NEWSROOM_MIN_SIGNAL_SCORE", 0.42),
            auto_publish_signal_min=_f("NEWSROOM_AUTO_PUBLISH_SIGNAL_MIN", 0.72),
            min_trust_score=_f("NEWSROOM_MIN_TRUST_SCORE", 0.55),
            force_manual_review=False,
            max_publishes_per_hour_hint=999,
        )
    return SoftLaunchThresholds(
        min_signal_score=max(0.48, _f("NEWSROOM_MIN_SIGNAL_SCORE", 0.42) + 0.06),
        auto_publish_signal_min=max(0.78, _f("NEWSROOM_AUTO_PUBLISH_SIGNAL_MIN", 0.72) + 0.06),
        min_trust_score=max(0.62, _f("NEWSROOM_MIN_TRUST_SCORE", 0.55) + 0.07),
        force_manual_review=True,
        max_publishes_per_hour_hint=int(os.getenv("SOFT_LAUNCH_MAX_PUBLISHES_PER_HOUR", "8")),
    )


def _f(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default
