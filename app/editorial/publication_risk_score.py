"""Publication risk score — high risk forces manual review."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.editorial.scoring_engine import EditorialScore, score_story
from app.editorial.signal_ranking import rank_story_signal
from app.editorial.source_tiers import aggregate_source_tier
from app.editorial.tone_engine import count_sensational_markers
from app.editorial.trust_system import evaluate_editorial_trust

_HIGH_RISK_THRESHOLD = 0.62


@dataclass(frozen=True)
class PublicationRiskScore:
    score: float
    mandatory_review: bool
    factors: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 4),
            "mandatory_review": self.mandatory_review,
            "factors": list(self.factors),
        }


def score_publication_risk(
    text: str,
    *,
    sources: list[str] | None = None,
    runtime_dir: str | None = None,
) -> PublicationRiskScore:
    chans = list(sources or [])
    unique = len({s.strip().lower() for s in chans if s.strip()})
    tier = aggregate_source_tier(chans, runtime_dir=runtime_dir)
    escore = score_story(text=text, sources=chans, runtime_dir=runtime_dir)
    trust = evaluate_editorial_trust(text, escore, sources=chans, runtime_dir=runtime_dir)
    signal = rank_story_signal(text, escore, sources=chans, runtime_dir=runtime_dir)

    factors: list[str] = []
    risk = 0.0

    risk += (1.0 - trust.trust_score) * 0.35
    if trust.trust_score < 0.55:
        factors.append("low_trust")

    risk += trust.rumor_risk * 0.25
    if trust.rumor_risk >= 0.5:
        factors.append("rumor_risk")

    risk += min(0.2, signal.sensationalism_penalty)
    if signal.sensationalism_penalty >= 0.35:
        factors.append("sensationalism")

    if count_sensational_markers(text) >= 2:
        risk += 0.12
        factors.append("tone_markers")

    if unique < 2:
        risk += 0.15
        factors.append("single_source")
    if tier.tier >= 3:
        risk += 0.12
        factors.append("tier3_source")

    if trust.controversial_escalation:
        risk += 0.18
        factors.append("controversial")

    if trust.source_contradiction:
        risk += 0.22
        factors.append("contradiction")

    risk = round(max(0.0, min(1.0, risk)), 4)
    mandatory = risk >= _HIGH_RISK_THRESHOLD or trust.manual_review_required
    return PublicationRiskScore(score=risk, mandatory_review=mandatory, factors=tuple(dict.fromkeys(factors)))
