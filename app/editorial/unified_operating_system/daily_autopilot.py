"""Daily Editorial Autopilot — 4 operating modes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class AutopilotMode(str, Enum):
    SIGNAL = "signal_mode"
    INTELLIGENCE = "intelligence_mode"
    COMPRESSION = "compression_mode"
    CONTINUITY = "continuity_mode"


@dataclass(frozen=True)
class AutopilotDecision:
    mode: AutopilotMode
    immediate_publish: bool
    use_csim: bool
    stability_fill: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "immediate_publish": self.immediate_publish,
            "use_csim": self.use_csim,
            "stability_fill": self.stability_fill,
            "reason": self.reason,
        }


def resolve_autopilot_mode(
    *,
    is_breaking: bool,
    gravity_total: float,
    anti_pause_active: bool,
    publishing_mode: str,
    cluster_size: int,
    quality_score: float,
    compression_required: bool,
) -> AutopilotDecision:
    if is_breaking or gravity_total >= 82:
        return AutopilotDecision(
            mode=AutopilotMode.SIGNAL,
            immediate_publish=True,
            use_csim=False,
            stability_fill=False,
            reason="high_gravity_or_breaking",
        )

    if publishing_mode in {"elastic_fill", "editorial_synthesis"} or anti_pause_active:
        return AutopilotDecision(
            mode=AutopilotMode.CONTINUITY,
            immediate_publish=False,
            use_csim=publishing_mode == "elastic_fill" and cluster_size >= 2,
            stability_fill=True,
            reason="anti_pause_continuity",
        )

    if compression_required or (cluster_size >= 2 and quality_score < 55):
        return AutopilotDecision(
            mode=AutopilotMode.COMPRESSION,
            immediate_publish=False,
            use_csim=True,
            stability_fill=False,
            reason="multi_signal_compression",
        )

    return AutopilotDecision(
        mode=AutopilotMode.INTELLIGENCE,
        immediate_publish=False,
        use_csim=False,
        stability_fill=False,
        reason="standard_intelligence_flow",
    )
