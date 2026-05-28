"""Signal-first news ranking — impact over volume."""

from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass
from typing import Any

from app.editorial.identity import load_editorial_identity
from app.editorial.scoring_engine import EditorialScore
from app.editorial.source_tiers import aggregate_source_tier

_OUTRAGE = re.compile(
    r"(возмущ|outrage|скандал\s+вокруг|шокирующ|позор|унизил|разнесли\s+в\s+соц)",
    re.I,
)
_GOSSIP = re.compile(r"(сплетн|gossip|who\s+dated|развод\s+звезд)", re.I)
_MEME_ECON = re.compile(r"(мемкоин|meme\s+coin|pump\s+and\s+dump|100x)", re.I)
_SENSATIONAL = re.compile(
    r"(срочно\s+узнай|you\s+won't\s+believe|это\s+изменит\s+всё|gone\s+wild)",
    re.I,
)
_POLITICS_SENSITIVE = re.compile(
    r"(выборы|election|impeach|отставк[аи]\s+премьер|госпереворот|coup|"
    r"политическ\w+\s+кризис|partisan|партийн)",
    re.I,
)


def _min_signal_score() -> float:
    try:
        return max(0.2, min(0.85, float(os.getenv("NEWSROOM_MIN_SIGNAL_SCORE", "0.42"))))
    except ValueError:
        return 0.42


@dataclass(frozen=True)
class SignalRankResult:
    signal_score: float
    impact: float
    relevance: float
    novelty: float
    authority: float
    shareability: float
    editorial_usefulness: float
    sensationalism_penalty: float
    niche_fit: float
    source_tier: int
    reject_reason: str | None = None
    manual_review_hint: bool = False

    @property
    def publish_signal_ok(self) -> bool:
        return self.reject_reason is None and self.signal_score >= _min_signal_score()

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["min_signal_threshold"] = _min_signal_score()
        d["publish_signal_ok"] = self.publish_signal_ok
        return d


def _novelty_from_text(text: str) -> float:
    words = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9]{4,}", (text or "").lower())
    if len(words) < 6:
        return 0.2
    return round(min(1.0, 0.25 + 0.75 * (len(set(words)) / len(words))), 4)


def _shareability(clarity: float, text: str) -> float:
    t = (text or "").strip()
    length_ok = 80 <= len(t) <= 1200
    return round(min(1.0, clarity * 0.7 + (0.3 if length_ok else 0.1)), 4)


def rank_story_signal(
    text: str,
    escore: EditorialScore,
    *,
    sources: list[str] | None = None,
    runtime_dir: str | None = None,
    category: str = "macro",
    clarity: float | None = None,
) -> SignalRankResult:
    """
    Composite signal score for publish triage.
    trust > quality > speed — low signal never auto-amplified.
    """
    identity = load_editorial_identity()
    tier_info = aggregate_source_tier(sources, runtime_dir=runtime_dir)

    impact = round(float(escore.impact_score), 4)
    relevance = round(float(escore.relevance_score), 4)
    novelty = _novelty_from_text(text)
    authority = tier_info.authority
    clarity_v = clarity if clarity is not None else min(1.0, len((text or "").strip()) / 400.0)
    shareability = _shareability(clarity_v, text)
    usefulness = round(
        min(1.0, impact * 0.4 + relevance * 0.35 + (1.0 if tier_info.tier <= 2 else 0.5) * 0.25),
        4,
    )

    sensationalism = 0.0
    if _SENSATIONAL.search(text or ""):
        sensationalism += 0.35
    if _OUTRAGE.search(text or ""):
        sensationalism += 0.25
    if _GOSSIP.search(text or ""):
        sensationalism += 0.3
    if _MEME_ECON.search(text or ""):
        sensationalism += 0.4
    sensationalism = round(min(0.9, sensationalism), 4)

    niche_fit = 1.0 if identity.matches_niche(category) else 0.55
    if identity.exclude_general_feed and category in {"noise", "reject"}:
        niche_fit = 0.1

    raw = (
        impact * 0.22
        + relevance * 0.20
        + novelty * 0.14
        + authority * 0.18
        + shareability * 0.10
        + usefulness * 0.16
    )
    raw = raw * niche_fit - sensationalism * 0.35
    if tier_info.tier >= 3:
        raw -= 0.06
    signal = round(max(0.0, min(1.0, raw)), 4)

    reject: str | None = None
    if _MEME_ECON.search(text or "") and impact < 0.5:
        reject = "meme_economics"
    elif _GOSSIP.search(text or "") and tier_info.tier >= 3:
        reject = "gossip_low_authority"
    elif sensationalism >= 0.5 and authority < 0.55:
        reject = "sensationalism_low_authority"
    manual = bool(
        _POLITICS_SENSITIVE.search(text or "")
        or (tier_info.tier >= 3 and signal < 0.58)
        or sensationalism >= 0.35
    )

    return SignalRankResult(
        signal_score=signal,
        impact=impact,
        relevance=relevance,
        novelty=novelty,
        authority=authority,
        shareability=shareability,
        editorial_usefulness=usefulness,
        sensationalism_penalty=sensationalism,
        niche_fit=niche_fit,
        source_tier=tier_info.tier,
        reject_reason=reject,
        manual_review_hint=manual,
    )
