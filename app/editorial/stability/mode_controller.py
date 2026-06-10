"""Publishing mode controller — Core / Elastic Fill / Editorial Synthesis."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.editorial.stability.anti_pause import AntiPauseStatus, evaluate_anti_pause
from app.editorial.stability.config import stability_layer_enabled


class PublishingMode(str, Enum):
    CORE = "core"
    ELASTIC_FILL = "elastic_fill"
    EDITORIAL_SYNTHESIS = "editorial_synthesis"


@dataclass(frozen=True)
class StabilityContext:
    mode: PublishingMode
    anti_pause: AntiPauseStatus
    bypass_governance: bool
    skip_cadence_cap: bool
    allow_synthesis: bool
    trigger_reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "anti_pause": self.anti_pause.to_dict(),
            "bypass_governance": self.bypass_governance,
            "skip_cadence_cap": self.skip_cadence_cap,
            "allow_synthesis": self.allow_synthesis,
            "trigger_reason": self.trigger_reason,
        }


def resolve_publishing_mode(
    *,
    newsroom_tz: str = "Europe/Moscow",
    cluster_size: int = 0,
    governance_blocked: bool = False,
    desk_blocked: bool = False,
    no_raw_posts: bool = False,
) -> StabilityContext:
    if not stability_layer_enabled():
        ap = evaluate_anti_pause(newsroom_tz=newsroom_tz)
        return StabilityContext(
            mode=PublishingMode.CORE,
            anti_pause=ap,
            bypass_governance=False,
            skip_cadence_cap=False,
            allow_synthesis=False,
            trigger_reason="stability_disabled",
        )

    ap = evaluate_anti_pause(newsroom_tz=newsroom_tz)
    from app.editorial.stability.config import (
        governance_bypass_on_anti_pause,
        skip_cadence_cap_on_anti_pause,
    )

    mode = PublishingMode.CORE
    trigger = "core_flow"
    bypass_gov = False
    skip_cap = False
    allow_synth = False

    if ap.anti_pause_active:
        if no_raw_posts or (desk_blocked and governance_blocked):
            mode = PublishingMode.EDITORIAL_SYNTHESIS
            trigger = ap.reason
            allow_synth = True
        elif governance_blocked or cluster_size < 1 or desk_blocked:
            mode = PublishingMode.ELASTIC_FILL
            trigger = ap.reason
            bypass_gov = governance_bypass_on_anti_pause() and governance_blocked
            skip_cap = skip_cadence_cap_on_anti_pause()
        elif ap.max_gap_exceeded:
            mode = PublishingMode.ELASTIC_FILL
            trigger = "max_gap_exceeded"
            skip_cap = skip_cadence_cap_on_anti_pause()
    elif governance_blocked and not ap.in_active_hours:
        mode = PublishingMode.CORE
        trigger = "offhours_governance_block"

    return StabilityContext(
        mode=mode,
        anti_pause=ap,
        bypass_governance=bypass_gov,
        skip_cadence_cap=skip_cap,
        allow_synthesis=allow_synth or (ap.max_gap_exceeded and no_raw_posts),
        trigger_reason=trigger,
    )


def primary_governance_suppress_reason(
    reason_codes: list[str],
    div_codes: list[str],
    gov_reason: str = "",
) -> str:
    """Resolve real suppress cause for telemetry (not first ranking tag)."""
    if gov_reason:
        return gov_reason
    for code in div_codes:
        if code in {"source_on_cooldown", "topic_on_cooldown"}:
            return code
    for code in div_codes:
        if code in {"source_cooldown", "topic_cooldown"}:
            return code
    for code in reason_codes:
        if code not in {"trusted_sources", "high_freshness", "operator_source_boost", "operator_topic_boost"}:
            return code
    if div_codes:
        return div_codes[0]
    return reason_codes[0] if reason_codes else "governance"


def should_bypass_governance(
    stability: StabilityContext,
    *,
    div_blocked: bool,
    gov_suppress: bool,
    hard_block: bool = False,
) -> bool:
    if hard_block:
        return False
    if not stability.bypass_governance:
        return False
    if not (div_blocked or gov_suppress):
        return False
    return stability.mode in {PublishingMode.ELASTIC_FILL, PublishingMode.EDITORIAL_SYNTHESIS}
