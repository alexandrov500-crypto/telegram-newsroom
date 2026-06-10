"""Zero-gap continuity controller — fallback chain when gap exceeds SLO."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.editorial.osgcp.config import max_gap_minutes, target_gap_minutes
from app.editorial.osgcp.attention_buffer import BufferMode, build_buffered_narrative


@dataclass(frozen=True)
class ContinuityAction:
    triggered: bool
    mode_used: str
    post_generated: bool
    fallback_chain_used: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "triggered": self.triggered,
            "mode_used": self.mode_used,
            "post_generated": self.post_generated,
            "fallback_chain_used": list(self.fallback_chain_used),
        }


def evaluate_continuity(
    *,
    runtime_dir: str | None,
    gap_minutes: float | None,
    pg_total: float,
    gravity_total: float,
    crs_total: float,
    can_publish: bool,
) -> ContinuityAction:
    gap = gap_minutes if gap_minutes is not None else 0.0
    target = target_gap_minutes()
    hard_max = max_gap_minutes()

    if gap < target or can_publish:
        return ContinuityAction(False, "none", False, ())

    chain: list[str] = []

    if pg_total >= 65:
        chain.append("peos_publish")
        return ContinuityAction(True, "peos_publish", True, tuple(chain))

    if gravity_total >= 60:
        chain.append("egdl_boost")
        return ContinuityAction(True, "egdl_boost_digest", True, tuple(chain))

    if crs_total >= 50:
        chain.append("auh_compression")
        return ContinuityAction(True, "auh_compression", True, tuple(chain))

    narrative = build_buffered_narrative(runtime_dir, prefer_mode=BufferMode.SYNTHESIS)
    if narrative:
        chain.append("synthesis_from_buffer")
        return ContinuityAction(True, narrative.mode.value, True, tuple(chain))

    if gap >= hard_max:
        chain.extend(["synthesis_fallback", "anti_pause_hard"])
        return ContinuityAction(True, "synthesis_fallback", False, tuple(chain))

    chain.append("wait_next_tick")
    return ContinuityAction(True, "wait_next_tick", False, tuple(chain))
