"""Simulate hub channel vs Telegram ecosystem competitors."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.editorial.gmcs.ecosystem_registry import ECOSYSTEM_COMPETITORS, competitors_for_vertical


@dataclass(frozen=True)
class CompetitiveMatchResult:
    competitor_label: str
    archetype: str
    our_win_probability: float
    channels_replaced: int
    advantage_reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "competitor_label": self.competitor_label,
            "archetype": self.archetype,
            "our_win_probability": round(self.our_win_probability, 3),
            "channels_replaced": self.channels_replaced,
            "advantage_reason": self.advantage_reason,
        }


@dataclass(frozen=True)
class EcosystemSimulationResult:
    vertical: str
    matches: tuple[CompetitiveMatchResult, ...]
    aggregate_win_rate: float
    channels_substituted_estimate: int
    competitive_moat_score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "vertical": self.vertical,
            "matches": [m.to_dict() for m in self.matches],
            "aggregate_win_rate": round(self.aggregate_win_rate, 3),
            "channels_substituted_estimate": self.channels_substituted_estimate,
            "competitive_moat_score": round(self.competitive_moat_score, 2),
        }


def simulate_ecosystem_competition(
    *,
    vertical: str = "macro",
    substitution_score: float = 50.0,
    dual_audience_trust: float = 0.5,
    imri_score: float = 50.0,
    cross_domain: bool = False,
) -> EcosystemSimulationResult:
    relevant = competitors_for_vertical(vertical) or list(ECOSYSTEM_COMPETITORS[:5])
    matches: list[CompetitiveMatchResult] = []

    hub_strength = (
        substitution_score * 0.35
        + dual_audience_trust * 100 * 0.25
        + imri_score * 0.30
        + (15.0 if cross_domain else 0.0)
    ) / 100.0

    for comp in relevant[:6]:
        vuln = comp.substitution_vulnerability
        freq_penalty = min(0.15, comp.publish_frequency_per_day / 100.0)
        win = min(0.98, hub_strength * vuln - freq_penalty + 0.1)
        win = max(0.05, win)

        reason = "cross_domain_synthesis" if cross_domain else "substitution_density"
        if dual_audience_trust >= 0.6:
            reason = "dual_audience_trust"

        matches.append(
            CompetitiveMatchResult(
                competitor_label=comp.label,
                archetype=comp.archetype.value,
                our_win_probability=win,
                channels_replaced=1 if win >= 0.55 else 0,
                advantage_reason=reason,
            )
        )

    wins = [m.our_win_probability for m in matches]
    agg = sum(wins) / len(wins) if wins else 0.0
    replaced = sum(m.channels_replaced for m in matches)
    moat = min(100.0, agg * 100 * 0.7 + substitution_score * 0.3)

    return EcosystemSimulationResult(
        vertical=vertical,
        matches=tuple(matches),
        aggregate_win_rate=agg,
        channels_substituted_estimate=replaced,
        competitive_moat_score=moat,
    )
