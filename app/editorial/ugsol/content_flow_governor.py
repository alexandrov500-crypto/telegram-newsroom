"""Autonomous content flow governor — spacing, format distribution, synthesis."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.editorial.stability.anti_pause import evaluate_anti_pause
from app.editorial.ugsol.config import digest_per_day_max, flagship_per_day_max, max_gap_minutes, target_gap_minutes
from app.editorial.ugsol.state import today_format_counts


class ForcedMode(str, Enum):
    NONE = "none"
    DIGEST = "digest"
    SYNTHESIS = "synthesis"
    SIGNAL = "signal"
    CONTEXT = "context"
    EXPLAINER = "explainer"


@dataclass(frozen=True)
class FlowDecision:
    allow_publish: bool
    forced_mode_override: ForcedMode
    inserted_synthesis: bool
    spacing_adjustment_minutes: int
    gap_minutes: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "allow_publish": self.allow_publish,
            "forced_mode_override": self.forced_mode_override.value,
            "inserted_synthesis": self.inserted_synthesis,
            "spacing_adjustment_minutes": self.spacing_adjustment_minutes,
            "gap_minutes": round(self.gap_minutes, 1),
            "reason": self.reason,
            "constraints": {
                "max_gap_min": max_gap_minutes(),
                "target_gap_min": target_gap_minutes(),
                "flagship_per_day_max": flagship_per_day_max(),
                "digest_per_day_max": digest_per_day_max(),
            },
        }


def evaluate_content_flow(
    *,
    runtime_dir: str | None,
    newsroom_tz: str = "Europe/Moscow",
    proposed_mode: str = "context",
    is_flagship: bool = False,
    is_breaking: bool = False,
    starvation: bool = False,
    signal_overload: bool = False,
) -> FlowDecision:
    ap = evaluate_anti_pause(newsroom_tz=newsroom_tz)
    gap = ap.publish_gap_minutes
    counts = today_format_counts(runtime_dir)
    flagship_today = int(counts.get("flagship") or 0)
    digest_today = int(counts.get("digest") or 0)
    signal_today = int(counts.get("signal") or 0)

    forced = ForcedMode.NONE
    allow = True
    synthesis = False
    spacing_adj = 0
    reason = "normal_flow"

    if gap >= max_gap_minutes() or ap.anti_pause_active:
        forced = ForcedMode.SYNTHESIS if starvation else ForcedMode.DIGEST
        synthesis = starvation or ap.anti_pause_active
        allow = True
        spacing_adj = -max(0, int(gap - target_gap_minutes()))
        reason = "anti_pause_or_max_gap"

    elif gap >= target_gap_minutes():
        allow = True
        spacing_adj = -int(gap - target_gap_minutes())
        reason = "pre_target_gap_acceleration"

    if is_flagship and flagship_today >= flagship_per_day_max():
        allow = False
        reason = "flagship_daily_cap"

    if proposed_mode == "digest" and digest_today >= digest_per_day_max() and not ap.anti_pause_active:
        forced = ForcedMode.CONTEXT
        reason = "digest_daily_cap"

    if signal_overload and signal_today >= 4 and not is_breaking:
        forced = ForcedMode.DIGEST
        reason = "signal_overload_prevention"

    if starvation and not is_breaking:
        forced = ForcedMode.SYNTHESIS
        synthesis = True
        allow = True
        reason = "starvation_synthesis_inject"

    if is_breaking:
        forced = ForcedMode.SIGNAL
        allow = True
        reason = "breaking_priority"

    return FlowDecision(
        allow_publish=allow,
        forced_mode_override=forced,
        inserted_synthesis=synthesis,
        spacing_adjustment_minutes=spacing_adj,
        gap_minutes=gap,
        reason=reason,
    )
