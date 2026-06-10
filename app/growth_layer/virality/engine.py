"""Pre-publish virality score — thin layer over SignalRankResult + EditorialScore."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any

from app.editorial.scoring_engine import EditorialScore
from app.editorial.signal_ranking import SignalRankResult
from app.growth_layer.virality.tiers import ViralityTier, classify_virality_tier

_MACRO_DIGIT = re.compile(
    r"(\d+[,.]?\d*\s*(?:%|б\.?\s*п\.?|bp|bps|₽|\$|€|trln|трлн|млрд|bn|mln|млн))"
    r"|(?:\bcpi\b|\bgdp\b|\bцб\b|\bfed\b|ключев\w*\s+ставк)",
    re.I,
)

_MODEL_VERSION = "v1-heuristic-signal-bridge"


def growth_layer_enabled() -> bool:
    raw = os.getenv("GROWTH_LAYER_ENABLED", "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class ViralityScoreResult:
    score: int
    tier: ViralityTier
    dimensions: dict[str, float]
    reasons: tuple[str, ...] = field(default_factory=tuple)
    model_version: str = _MODEL_VERSION

    def to_growth_extras_patch(self, *, format_profile: str) -> dict[str, Any]:
        return {
            "growth": {
                "virality_score": self.score,
                "virality_tier": self.tier.value,
                "format_profile": format_profile,
                "dimensions": dict(self.dimensions),
                "reasons": list(self.reasons)[:8],
                "model_version": self.model_version,
            }
        }


class ViralityScoreEngine:
    """
    Maps existing signal/editorial scores → 0–100 virality score.
    Does not replace ``rank_story_signal`` or desk_filter.
    """

    def score(
        self,
        *,
        text: str,
        signal: SignalRankResult,
        escore: EditorialScore | None = None,
        editorial_card: dict[str, Any] | None = None,
    ) -> ViralityScoreResult:
        dup_penalty = 0.0
        if editorial_card:
            dup_penalty = min(0.35, float(editorial_card.get("duplicate_confidence") or 0.0))

        novelty = max(0.0, min(1.0, float(signal.novelty) * (1.0 - dup_penalty * 0.5)))

        impact_raw = float(signal.impact)
        if escore is not None:
            impact_raw = max(impact_raw, float(escore.impact_score))
        macro_boost = 0.12 if _MACRO_DIGIT.search(text or "") else 0.0
        economic_impact = max(0.0, min(1.0, impact_raw + macro_boost))

        audience_relevance = max(
            0.0,
            min(
                1.0,
                float(signal.niche_fit) * 0.45
                + float(signal.relevance) * 0.35
                + float(signal.editorial_usefulness) * 0.2,
            ),
        )

        sensationalism = float(signal.sensationalism_penalty)
        emotional_trigger = max(
            0.0,
            min(1.0, float(signal.attention_potential) * 0.55 + float(signal.reaction_potential) * 0.25 - sensationalism * 0.6),
        )

        shareability = max(
            0.0,
            min(
                1.0,
                float(signal.shareability) * 0.35
                + float(signal.forwardability) * 0.25
                + float(signal.repost_probability) * 0.25
                + float(signal.screenshotability) * 0.08
                + float(signal.quoteability) * 0.07,
            ),
        )

        raw = (
            novelty * 0.22
            + economic_impact * 0.24
            + audience_relevance * 0.22
            + emotional_trigger * 0.14
            + shareability * 0.18
        )
        score = int(round(max(0.0, min(100.0, raw * 100.0))))
        tier = classify_virality_tier(score)

        reasons: list[str] = []
        if tier is ViralityTier.VIRAL_CANDIDATE:
            reasons.append("viral_candidate_band")
        if economic_impact >= 0.65:
            reasons.append("high_economic_impact")
        if shareability >= 0.6:
            reasons.append("high_shareability")
        if signal.repost_probability >= 0.55:
            reasons.append("high_repost_probability")
        if sensationalism >= 0.35:
            reasons.append("sensationalism_penalty_applied")

        return ViralityScoreResult(
            score=score,
            tier=tier,
            dimensions={
                "novelty": round(novelty, 4),
                "economic_impact": round(economic_impact, 4),
                "audience_relevance": round(audience_relevance, 4),
                "emotional_trigger": round(emotional_trigger, 4),
                "shareability": round(shareability, 4),
            },
            reasons=tuple(reasons),
        )
