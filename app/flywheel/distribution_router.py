"""Multi-surface distribution routing."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from typing import Any


class DistributionSurface(str, Enum):
    MAIN = "main"
    BREAKING = "breaking"
    DIGEST = "digest"
    DISCARD = "discard"
    EXPORT = "export"


@dataclass(frozen=True)
class RoutingDecision:
    surface: DistributionSurface
    channel_id: int
    reason: str
    also_digest: bool
    priority: int


def _channel_env(name: str, fallback: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return fallback
    try:
        return int(raw)
    except ValueError:
        return fallback


def route_distribution_surface(
    settings: Any,
    *,
    is_breaking: bool = False,
    insight_score: float = 0.0,
    style_score: float = 0.0,
    signal_score: float = 0.0,
    tags: list[str] | None = None,
) -> RoutingDecision:
    """
    Decision tree:
      breaking + high urgency → BREAKING channel
      insight≥0.7 + style≥0.65 → MAIN + digest flag
      insight≥0.55 → MAIN
      insight<0.45 → DISCARD (caller may override)
      deep insight only → DIGEST-only path via also_digest without main (handled by caller)
    """
    main = int(getattr(settings, "target_channel_id", 0) or 0)
    breaking_ch = _channel_env("TELEGRAM_BREAKING_CHANNEL_ID", main)
    digest_ch = _channel_env("TELEGRAM_DIGEST_CHANNEL_ID", main)

    if is_breaking:
        return RoutingDecision(
            DistributionSurface.BREAKING,
            breaking_ch,
            "breaking_lane",
            also_digest=False,
            priority=100,
        )

    if insight_score < 0.42 and signal_score < 0.5:
        return RoutingDecision(
            DistributionSurface.DISCARD,
            main,
            "low_signal_insight",
            also_digest=False,
            priority=0,
        )

    also_digest = insight_score >= 0.68 and style_score >= 0.62
    priority = int(50 + insight_score * 30 + style_score * 20)

    if insight_score >= 0.72 and style_score >= 0.65:
        return RoutingDecision(
            DistributionSurface.MAIN,
            main,
            "high_signal_main",
            also_digest=True,
            priority=priority,
        )

    return RoutingDecision(
        DistributionSurface.MAIN,
        main,
        "standard_main",
        also_digest=also_digest,
        priority=priority,
    )


def resolve_channel_id(decision: RoutingDecision) -> int:
    return int(decision.channel_id)
