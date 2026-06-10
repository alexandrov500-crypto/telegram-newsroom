"""Unified editorial arbitration — OSGCP final shipping decision."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.editorial.osgcp.config import max_gap_minutes, target_gap_minutes
from app.editorial.osgcp.state_machine import EditorialStateKind


class EditorialAction(str, Enum):
    PUBLISH = "publish"
    DIGEST = "digest"
    SYNTHESIZE = "synthesize"
    REJECT = "reject"
    PRIORITY_BOOST = "priority_boost"


class FormatMode(str, Enum):
    SIGNAL = "signal"
    CONTEXT = "context"
    DIGEST = "digest"
    EXPLAINER = "explainer"


class OverrideSource(str, Enum):
    STABILITY = "stability"
    GROWTH = "growth"
    HYBRID = "hybrid"
    PRODUCT = "product"


@dataclass(frozen=True)
class EditorialDecision:
    action: EditorialAction
    format_mode: FormatMode
    override_source: OverrideSource
    reasoning_trace: tuple[str, ...] = field(default_factory=tuple)
    force_digest: bool = False
    priority_boost: bool = False
    stability_override: bool = False
    reject: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action.value,
            "format_mode": self.format_mode.value,
            "override_source": self.override_source.value,
            "reasoning_trace": list(self.reasoning_trace),
            "force_digest": self.force_digest,
            "priority_boost": self.priority_boost,
            "stability_override": self.stability_override,
            "reject": self.reject,
        }


def arbitrate_editorial_decision(
    *,
    editorial_state: EditorialStateKind,
    pg_total: float,
    gravity_total: float,
    crs_total: float,
    continuity_score: float,
    source_independence: float,
    gap_minutes: float | None,
    peos_reject: bool = False,
    ueos_reject: bool = False,
    publishing_mode: str = "core",
) -> EditorialDecision:
    trace: list[str] = []
    gap = gap_minutes if gap_minutes is not None else 0.0
    max_gap = max_gap_minutes()

    if editorial_state == EditorialStateKind.ANTI_PAUSE or gap >= max_gap:
        trace.append("stability:anti_pause_or_max_gap")
        return EditorialDecision(
            action=EditorialAction.DIGEST,
            format_mode=FormatMode.DIGEST,
            override_source=OverrideSource.STABILITY,
            reasoning_trace=tuple(trace),
            force_digest=True,
            stability_override=True,
            reject=False,
        )

    if editorial_state == EditorialStateKind.SYNTHESIS:
        trace.append("stability:synthesis_state")
        return EditorialDecision(
            action=EditorialAction.SYNTHESIZE,
            format_mode=FormatMode.DIGEST,
            override_source=OverrideSource.STABILITY,
            reasoning_trace=tuple(trace),
            force_digest=True,
            stability_override=True,
        )

    if editorial_state == EditorialStateKind.SIGNAL and gravity_total >= 75:
        trace.append("growth:high_gravity_signal")
        return EditorialDecision(
            action=EditorialAction.PRIORITY_BOOST,
            format_mode=FormatMode.SIGNAL,
            override_source=OverrideSource.GROWTH,
            reasoning_trace=tuple(trace),
            priority_boost=True,
        )

    if pg_total >= 85:
        trace.append("product:pg_flagship")
        return EditorialDecision(
            action=EditorialAction.PRIORITY_BOOST,
            format_mode=FormatMode.SIGNAL if gravity_total >= 70 else FormatMode.CONTEXT,
            override_source=OverrideSource.PRODUCT,
            reasoning_trace=tuple(trace),
            priority_boost=True,
        )

    if peos_reject or ueos_reject:
        if gap >= target_gap_minutes() or continuity_score < 0.6:
            trace.append("hybrid:product_reject_overridden_by_continuity")
            return EditorialDecision(
                action=EditorialAction.DIGEST,
                format_mode=FormatMode.CONTEXT,
                override_source=OverrideSource.HYBRID,
                reasoning_trace=tuple(trace),
                force_digest=True,
                stability_override=True,
                reject=False,
            )
        if publishing_mode != "core":
            trace.append("stability:non_core_digest_fallback")
            return EditorialDecision(
                action=EditorialAction.DIGEST,
                format_mode=FormatMode.DIGEST,
                override_source=OverrideSource.STABILITY,
                reasoning_trace=tuple(trace),
                force_digest=True,
                reject=False,
            )
        trace.append("product:reject_confirmed")
        return EditorialDecision(
            action=EditorialAction.REJECT,
            format_mode=FormatMode.CONTEXT,
            override_source=OverrideSource.PRODUCT,
            reasoning_trace=tuple(trace),
            reject=True,
        )

    if editorial_state == EditorialStateKind.LOW_SIGNAL or crs_total < 55:
        trace.append("auh:low_signal_digest")
        return EditorialDecision(
            action=EditorialAction.DIGEST,
            format_mode=FormatMode.DIGEST,
            override_source=OverrideSource.HYBRID,
            reasoning_trace=tuple(trace),
            force_digest=True,
        )

    if pg_total >= 70 and crs_total >= 60:
        trace.append("product:publish_clear")
        fmt = FormatMode.SIGNAL if gravity_total >= 72 else FormatMode.CONTEXT
        return EditorialDecision(
            action=EditorialAction.PUBLISH,
            format_mode=fmt,
            override_source=OverrideSource.PRODUCT,
            reasoning_trace=tuple(trace),
        )

    if source_independence < 0.5 and pg_total < 78:
        trace.append("growth:single_source_digest")
        return EditorialDecision(
            action=EditorialAction.DIGEST,
            format_mode=FormatMode.CONTEXT,
            override_source=OverrideSource.GROWTH,
            reasoning_trace=tuple(trace),
            force_digest=True,
        )

    trace.append("hybrid:default_publish")
    return EditorialDecision(
        action=EditorialAction.PUBLISH,
        format_mode=FormatMode.CONTEXT,
        override_source=OverrideSource.HYBRID,
        reasoning_trace=tuple(trace),
    )
