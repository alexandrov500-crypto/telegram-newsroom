"""Market Dominance Index — channel position vs ecosystem."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.editorial.gmcs.competitive_simulator import EcosystemSimulationResult
from app.editorial.gmcs.config import dominance_index_threshold


class DominanceTier(str, Enum):
    ECOSYSTEM_LEADER = "ecosystem_leader"
    STRONG_SUBSTITUTOR = "strong_substitutor"
    EMERGING = "emerging"
    VULNERABLE = "vulnerable"


@dataclass(frozen=True)
class MarketDominanceState:
    index: float
    tier: DominanceTier
    competitive_gap: float
    growth_headroom: float
    recommended_posture: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": round(self.index, 2),
            "tier": self.tier.value,
            "competitive_gap": round(self.competitive_gap, 3),
            "growth_headroom": round(self.growth_headroom, 3),
            "recommended_posture": self.recommended_posture,
        }


def compute_market_dominance(
    simulation: EcosystemSimulationResult,
    *,
    imri_score: float = 50.0,
) -> MarketDominanceState:
    mdi = simulation.competitive_moat_score * 0.55 + imri_score * 0.45
    gap = 1.0 - simulation.aggregate_win_rate
    headroom = max(0.0, (dominance_index_threshold() - mdi) / 100.0)

    if mdi >= dominance_index_threshold():
        tier = DominanceTier.ECOSYSTEM_LEADER
        posture = "aggressive_substitution_growth"
    elif mdi >= 60:
        tier = DominanceTier.STRONG_SUBSTITUTOR
        posture = "expand_cross_domain_flagship"
    elif mdi >= 45:
        tier = DominanceTier.EMERGING
        posture = "build_trust_reduce_noise"
    else:
        tier = DominanceTier.VULNERABLE
        posture = "recovery_imri_focus"

    return MarketDominanceState(
        index=mdi,
        tier=tier,
        competitive_gap=gap,
        growth_headroom=headroom,
        recommended_posture=posture,
    )
