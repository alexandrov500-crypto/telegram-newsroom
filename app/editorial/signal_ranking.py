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
_MOMENTUM_TOPICS = re.compile(
    r"(rate\s+hike|rate\s+cut|ключев.*ставк|inflation|инфляц|etf|liquidation|ликвидац|"
    r"geopolit|санкци|tariff|ai\s+model|chip|nvidia|tesla|bitcoin|btc|ethereum|eth\b|"
    r"flows?|поток\s+капитал|capital\s+flow|volatility|волатильн|default|crash|rally)",
    re.I,
)
_WEAK_CRYPTO_NOISE = re.compile(
    r"(moon|100x|gem|airdrop|referral|pump|signal\s+group|easy\s+profit|быстрый\s+профит)",
    re.I,
)
_OPEN_LOOP = re.compile(
    r"(дальше|далее|next|watch|следим|что\s+дальше|what\s+next|tomorrow|в\s+ближайшие|"
    r"рынок\s+жд[её]т|ожидается)",
    re.I,
)


def _min_signal_score() -> float:
    try:
        return max(0.2, min(0.9, float(os.getenv("NEWSROOM_MIN_SIGNAL_SCORE", "0.55"))))
    except ValueError:
        return 0.55


@dataclass(frozen=True)
class SignalRankResult:
    signal_score: float
    attention_potential: float
    repost_probability: float
    narrative_strength: float
    forwardability: float
    screenshotability: float
    quoteability: float
    reaction_potential: float
    narrative_cluster: str
    momentum_score: float
    growth_velocity: float
    saturation_level: float
    fatigue_probability: float
    time_of_day_fit: float
    priority_multiplier: float
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


def _attention_potential(text: str, *, impact: float, urgency: float) -> float:
    t = (text or "").strip()
    topic_boost = 0.18 if _MOMENTUM_TOPICS.search(t) else 0.04
    digit_boost = 0.1 if re.search(r"\d", t) else 0.0
    return round(min(1.0, 0.3 + impact * 0.3 + urgency * 0.22 + topic_boost + digit_boost), 4)


def _narrative_strength(text: str, *, relevance: float) -> float:
    t = (text or "").strip()
    sents = [s for s in re.split(r"(?<=[.!?])\s+", t) if len(s.strip()) > 12]
    has_flow = len(sents) >= 2
    has_open_loop = bool(_OPEN_LOOP.search(t))
    base = 0.35 + relevance * 0.35
    if has_flow:
        base += 0.14
    if has_open_loop:
        base += 0.1
    return round(min(1.0, base), 4)


def _repost_probability(
    text: str,
    *,
    attention: float,
    narrative: float,
    shareability: float,
    authority: float,
) -> float:
    t = (text or "").strip()
    screenshotability = 0.18 if re.search(r"(\d+[%$]|млрд|млн|bn|million|billion)", t, re.I) else 0.08
    return round(
        min(
            1.0,
            0.18 + attention * 0.28 + narrative * 0.2 + shareability * 0.18 + authority * 0.08 + screenshotability,
        ),
        4,
    )


def _screenshotability(text: str) -> float:
    t = text or ""
    has_numbers = bool(re.search(r"\d", t))
    has_big_units = bool(re.search(r"(млрд|млн|bn|million|billion|%)", t, re.I))
    sharp_len = 70 <= len(t.strip()) <= 850
    score = 0.28 + (0.32 if has_numbers else 0.12) + (0.25 if has_big_units else 0.08) + (0.15 if sharp_len else 0.05)
    return round(min(1.0, score), 4)


def _quoteability(text: str, narrative_strength: float) -> float:
    t = text or ""
    concise = len(t.strip()) <= 900
    has_assertive_line = bool(re.search(r"(это\s+значит|рынок\s+ждет|signals?|implies|drives?)", t, re.I))
    return round(
        min(1.0, 0.24 + narrative_strength * 0.42 + (0.2 if concise else 0.08) + (0.14 if has_assertive_line else 0.06)),
        4,
    )


def _reaction_potential(text: str, attention: float, urgency: float) -> float:
    t = text or ""
    fear_greed = bool(re.search(r"(volatility|risk|стресс|страх|эйфор|panic|rally|crash)", t, re.I))
    return round(min(1.0, 0.22 + attention * 0.42 + urgency * 0.24 + (0.12 if fear_greed else 0.06)), 4)


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
    attention = _attention_potential(text, impact=impact, urgency=float(escore.urgency_score))
    narrative_strength = _narrative_strength(text, relevance=relevance)
    repost_probability = _repost_probability(
        text,
        attention=attention,
        narrative=narrative_strength,
        shareability=shareability,
        authority=authority,
    )
    screenshotability = _screenshotability(text)
    quoteability = _quoteability(text, narrative_strength)
    reaction_potential = _reaction_potential(text, attention, float(escore.urgency_score))
    forwardability = round(min(1.0, repost_probability * 0.65 + quoteability * 0.2 + screenshotability * 0.15), 4)
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

    # Aggressive growth order: attention → repost → narrative → market relevance → speed → raw importance.
    raw = (
        0.12
        + attention * 0.2
        + repost_probability * 0.2
        + narrative_strength * 0.16
        + forwardability * 0.06
        + screenshotability * 0.04
        + quoteability * 0.03
        + reaction_potential * 0.02
        + relevance * 0.1
        + novelty * 0.08
        + shareability * 0.08
        + usefulness * 0.08
        + float(escore.urgency_score) * 0.05
        + impact * 0.03
        + authority * 0.02
    )
    narrative_cluster = ""
    momentum_score = 0.5
    growth_velocity = 0.5
    saturation_level = 0.5
    fatigue_probability = 0.5
    time_of_day_fit = 0.72
    priority_multiplier = 1.0
    if runtime_dir:
        try:
            from app.editorial.intelligence.trend_memory import (
                evaluate_narrative_strategy,
                infer_narrative_cluster,
                time_of_day_cluster_fit,
            )

            narrative_cluster = infer_narrative_cluster(text, category=category)
            trend = evaluate_narrative_strategy(runtime_dir, text=text, category=category)
            momentum_score = float(trend.get("momentum_score") or 0.5)
            growth_velocity = float(trend.get("growth_velocity") or 0.5)
            saturation_level = float(trend.get("saturation_level") or 0.5)
            fatigue_probability = float(trend.get("fatigue_probability") or 0.5)
            priority_multiplier = float(trend.get("priority_multiplier") or 1.0)
            time_of_day_fit = time_of_day_cluster_fit(runtime_dir, cluster_key=narrative_cluster)
        except Exception:
            narrative_cluster = ""
    raw = raw * priority_multiplier * (0.9 + time_of_day_fit * 0.1)
    raw = raw * niche_fit - sensationalism * 0.35
    if tier_info.tier >= 3:
        raw -= 0.06
    if _WEAK_CRYPTO_NOISE.search(text or "") and impact < 0.55:
        raw -= 0.16
    signal = round(max(0.0, min(1.0, raw)), 4)

    reject: str | None = None
    if _MEME_ECON.search(text or "") and impact < 0.5:
        reject = "meme_economics"
    elif _WEAK_CRYPTO_NOISE.search(text or "") and impact < 0.55:
        reject = "weak_crypto_noise"
    elif _GOSSIP.search(text or "") and tier_info.tier >= 3:
        reject = "gossip_low_authority"
    elif sensationalism >= 0.5 and authority < 0.55:
        reject = "sensationalism_low_authority"
    elif repost_probability < 0.4 and narrative_strength < 0.42 and signal < 0.55:
        reject = "low_forwardability"
    elif fatigue_probability >= 0.82 and forwardability < 0.5:
        reject = "narrative_fatigue"
    manual = bool(
        _POLITICS_SENSITIVE.search(text or "")
        or (tier_info.tier >= 3 and signal < 0.58)
        or sensationalism >= 0.35
    )

    return SignalRankResult(
        signal_score=signal,
        attention_potential=attention,
        repost_probability=repost_probability,
        narrative_strength=narrative_strength,
        forwardability=forwardability,
        screenshotability=screenshotability,
        quoteability=quoteability,
        reaction_potential=reaction_potential,
        narrative_cluster=narrative_cluster,
        momentum_score=round(momentum_score, 4),
        growth_velocity=round(growth_velocity, 4),
        saturation_level=round(saturation_level, 4),
        fatigue_probability=round(fatigue_probability, 4),
        time_of_day_fit=round(time_of_day_fit, 4),
        priority_multiplier=round(priority_multiplier, 4),
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
