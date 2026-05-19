from __future__ import annotations

import re

from bot.editorial.story_types import ImportanceBreakdown, StorySnapshot, TrendPhase

_GEOPOLITICAL_RE = re.compile(
    r"\b(war|sanction|nato|election|invasion|ceasefire|missile|nuclear|"
    r"parliament|president|minister|embargo|conflict|troops|border)\b",
    re.I,
)
_MARKET_RE = re.compile(
    r"\b(etf|fed|rate hike|inflation|bitcoin|ethereum|nasdaq|s&p|"
    r"stock|market crash|rally|ipo|sec|treasury)\b",
    re.I,
)
_MAJOR_ENTITIES = frozenset(
    {
        "sec",
        "federal reserve",
        "openai",
        "nvidia",
        "apple",
        "microsoft",
        "google",
        "russia",
        "china",
        "united states",
        "european union",
        "bitcoin",
        "ethereum",
    }
)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def compute_importance(
    *,
    title: str,
    summary: str | None,
    tags: list[str],
    source_trust: float,
    source_count: int,
    entity_names: list[str],
    trend_velocity: float,
    language_count: int,
    cluster_variant_count: int,
    priority_score: float = 0.5,
) -> ImportanceBreakdown:
    text = f"{title} {summary or ''} {' '.join(tags)}".lower()

    corroboration = _clamp(min(1.0, source_count / 4.0))
    trust = _clamp(source_trust)

    entity_hits = sum(
        1 for name in entity_names if name.lower() in _MAJOR_ENTITIES
    )
    entity_weight = _clamp(0.35 + entity_hits * 0.12)

    geopolitical = 0.85 if _GEOPOLITICAL_RE.search(text) else 0.25
    market_impact = 0.8 if _MARKET_RE.search(text) else 0.3

    lang_spread = _clamp(language_count / 2.0)
    cluster_growth = _clamp(cluster_variant_count / 5.0)
    velocity = _clamp(trend_velocity)

    score = (
        trust * 0.18
        + corroboration * 0.16
        + entity_weight * 0.14
        + geopolitical * 0.14
        + market_impact * 0.12
        + velocity * 0.12
        + lang_spread * 0.06
        + cluster_growth * 0.08
    )
    score = max(score, priority_score * 0.35)
    return ImportanceBreakdown(
        importance_score=_clamp(score),
        source_trust=trust,
        corroboration=corroboration,
        entity_weight=entity_weight,
        geopolitical=geopolitical,
        market_impact=market_impact,
        trend_velocity=velocity,
        language_spread=lang_spread,
        cluster_growth=cluster_growth,
    )


def importance_tier(score: float) -> str:
    if score >= 0.9:
        return "breaking_global"
    if score >= 0.75:
        return "major"
    if score >= 0.5:
        return "medium"
    return "low"


def detect_trend_phase(
    *,
    trend_velocity: float,
    importance_score: float,
    hours_since_update: float,
) -> TrendPhase:
    if trend_velocity >= 0.85 and importance_score >= 0.75:
        return TrendPhase.BREAKING
    if trend_velocity >= 0.65:
        return TrendPhase.VIRAL
    if hours_since_update > 72 and trend_velocity >= 0.45:
        return TrendPhase.RESURFACING
    if hours_since_update > 48 and trend_velocity < 0.25:
        return TrendPhase.COOLING_DOWN
    return TrendPhase.STABLE


def recompute_story_status(
    story: StorySnapshot,
    *,
    trend_velocity: float,
    importance_score: float,
    hours_since_update: float,
) -> str:
    from bot.editorial.story_types import StoryStatus

    phase = detect_trend_phase(
        trend_velocity=trend_velocity,
        importance_score=importance_score,
        hours_since_update=hours_since_update,
    )
    if hours_since_update > 168:
        return StoryStatus.ARCHIVED.value
    if hours_since_update > 96 and phase == TrendPhase.COOLING_DOWN:
        return StoryStatus.COOLDOWN.value
    if phase in (TrendPhase.BREAKING, TrendPhase.VIRAL):
        return StoryStatus.TRENDING.value
    if story.status == StoryStatus.CREATED.value:
        return StoryStatus.ACTIVE.value
    return StoryStatus.ACTIVE.value
