"""Arbitration between Stability Layer and Growth Dominance Layer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ArbitrationWinner(str, Enum):
    STABILITY = "stability"
    GROWTH = "growth"
    HYBRID = "hybrid"


@dataclass(frozen=True)
class ArbitrationDecision:
    winner: ArbitrationWinner
    publish: bool
    force_digest: bool
    priority_boost: bool
    stability_override: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "winner": self.winner.value,
            "publish": self.publish,
            "force_digest": self.force_digest,
            "priority_boost": self.priority_boost,
            "stability_override": self.stability_override,
            "reason": self.reason,
        }


def arbitrate_stability_vs_growth(
    *,
    anti_pause_active: bool,
    silence_risk: bool,
    gravity_action: str,
    gravity_total: float,
    growth_reject: bool,
    attention_passes: bool,
    source_downgrade_digest: bool,
    publishing_mode: str = "core",
) -> ArbitrationDecision:
    if silence_risk or anti_pause_active:
        if gravity_action == "reject_or_synthesis" and publishing_mode != "core":
            return ArbitrationDecision(
                winner=ArbitrationWinner.STABILITY,
                publish=True,
                force_digest=True,
                priority_boost=False,
                stability_override=True,
                reason="silence_risk_stability_override",
            )
        if anti_pause_active and growth_reject:
            return ArbitrationDecision(
                winner=ArbitrationWinner.STABILITY,
                publish=True,
                force_digest=True,
                priority_boost=False,
                stability_override=True,
                reason="anti_pause_overrides_growth_reject",
            )

    if gravity_action == "priority_boost" and attention_passes:
        return ArbitrationDecision(
            winner=ArbitrationWinner.GROWTH,
            publish=True,
            force_digest=False,
            priority_boost=True,
            stability_override=False,
            reason="high_gravity_dominance",
        )

    if source_downgrade_digest or gravity_action == "digest_merge":
        return ArbitrationDecision(
            winner=ArbitrationWinner.GROWTH,
            publish=True,
            force_digest=True,
            priority_boost=False,
            stability_override=False,
            reason="digest_slot_routing",
        )

    if growth_reject or gravity_action == "reject_or_synthesis":
        return ArbitrationDecision(
            winner=ArbitrationWinner.GROWTH,
            publish=False,
            force_digest=False,
            priority_boost=False,
            stability_override=False,
            reason="growth_filter_reject",
        )

    return ArbitrationDecision(
        winner=ArbitrationWinner.HYBRID,
        publish=True,
        force_digest=False,
        priority_boost=gravity_total >= 70,
        stability_override=False,
        reason="hybrid_default_publish",
    )
