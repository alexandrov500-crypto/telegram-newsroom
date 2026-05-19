from __future__ import annotations

import re
from dataclasses import dataclass, field

from bot.editorial.importance import compute_importance
from bot.editorial.memory.topics import extract_topic_keys
from bot.editorial.priority.balance import compute_topic_balance, topic_bucket
from bot.editorial.priority.classification import classify_urgency
from bot.editorial.priority.confirmation import cross_source_confirmation_score
from bot.editorial.priority.entities import score_entity_significance
from bot.editorial.priority.momentum import compute_storyline_momentum
from bot.editorial.priority.noise import build_noise_warnings, detect_shallow_rewrite
from bot.editorial.quality.scoring import evaluate_editorial_quality

_GEOPOLITICAL_RE = re.compile(
    r"\b(war|sanction|nato|invasion|ceasefire|missile|nuclear|embargo|conflict)\b",
    re.I,
)
_MARKET_RE = re.compile(
    r"\b(etf|fed|rate hike|inflation|bitcoin|nasdaq|s&p|ipo|sec|treasury|earnings)\b",
    re.I,
)


@dataclass(frozen=True, slots=True)
class PriorityFactors:
    source_trust: float
    storyline_importance: float
    novelty: float
    market_impact: float
    geopolitical_impact: float
    audience_fatigue: float
    entity_significance: float
    topic_momentum: float
    cross_source_confirmation: float
    editorial_quality: float
    topic_balance_penalty: float = 0.0

    def to_dict(self) -> dict[str, float]:
        return {
            "source_trust": self.source_trust,
            "storyline_importance": self.storyline_importance,
            "novelty": self.novelty,
            "market_impact": self.market_impact,
            "geopolitical_impact": self.geopolitical_impact,
            "audience_fatigue": self.audience_fatigue,
            "entity_significance": self.entity_significance,
            "topic_momentum": self.topic_momentum,
            "cross_source_confirmation": self.cross_source_confirmation,
            "editorial_quality": self.editorial_quality,
            "topic_balance_penalty": self.topic_balance_penalty,
        }


@dataclass(frozen=True, slots=True)
class EditorialPriorityResult:
    editorial_priority_score: float
    urgency_class: str
    factors: PriorityFactors
    warnings: tuple[str, ...] = ()
    momentum: dict[str, float | str] = field(default_factory=dict)
    balance: dict[str, float] = field(default_factory=dict)
    why_ranked: tuple[str, ...] = ()
    entity_hits: tuple[str, ...] = ()


def _clamp(v: float) -> float:
    return max(0.0, min(1.0, v))


def compute_editorial_priority(
    *,
    headline: str,
    summary: str,
    tags: list[str],
    source: str | None,
    source_trust: float,
    source_count: int,
    variant_count: int,
    sources: tuple[str, ...] | list[str],
    memory_saturation: float = 0.0,
    memory_match_score: float = 0.0,
    follow_up_kind: str | None = None,
    storyline_publish_count: int = 0,
    recent_headlines: list[str] | None = None,
    recent_topic_buckets: list[str] | None = None,
    quality_score: float | None = None,
) -> EditorialPriorityResult:
    text = f"{headline} {summary}"
    topic_keys = extract_topic_keys(headline, summary, tags=tags)

    entity_score, entity_hits = score_entity_significance(headline, summary)
    geo = 0.82 if _GEOPOLITICAL_RE.search(text) else 0.28
    market = 0.8 if _MARKET_RE.search(text) else 0.3

    confirmation, _ = cross_source_confirmation_score(
        source=source,
        source_count=source_count,
        variant_count=variant_count,
        sources=sources,
        source_trust=source_trust,
    )

    momentum = compute_storyline_momentum(
        headline=headline,
        summary=summary,
        publish_count=storyline_publish_count,
        recent_headlines=recent_headlines or [],
        saturation=memory_saturation,
    )
    topic_momentum = float(momentum.get("storyline_momentum", 0.0))

    imp = compute_importance(
        title=headline,
        summary=summary,
        tags=tags,
        source_trust=source_trust,
        source_count=source_count,
        entity_names=entity_hits,
        trend_velocity=topic_momentum,
        language_count=1,
        cluster_variant_count=variant_count,
    )
    storyline_importance = _clamp(float(imp.importance_score))

    if quality_score is None:
        q = evaluate_editorial_quality(
            headline=headline,
            summary=summary,
            link="https://example.com",
            tags=tags,
            source=source,
            template_key="economy",
        )
        quality_score = q.editorial_quality_score
        information_density = q.information_density
    else:
        information_density = 0.55

    novelty = _clamp(1.0 - memory_match_score * 0.85)
    if follow_up_kind == "duplicate":
        novelty *= 0.35
    elif follow_up_kind == "minor_variation":
        novelty *= 0.55

    fatigue = _clamp(memory_saturation)
    bucket = topic_bucket(tags, topic_keys)
    balance = compute_topic_balance(
        candidate_bucket=bucket,
        recent_buckets=recent_topic_buckets or [],
    )
    balance_penalty = float(balance.get("topic_balance_penalty", 0.0))

    factors = PriorityFactors(
        source_trust=_clamp(source_trust),
        storyline_importance=storyline_importance,
        novelty=novelty,
        market_impact=market,
        geopolitical_impact=geo,
        audience_fatigue=fatigue,
        entity_significance=entity_score,
        topic_momentum=topic_momentum,
        cross_source_confirmation=confirmation,
        editorial_quality=_clamp(quality_score),
        topic_balance_penalty=balance_penalty,
    )

    category_recovery_boost = 0.0
    longtail_boost = 0.0
    try:
        from bot.editorial.flow_health.category_balance import recovery_category_adjustment

        category_recovery_boost = recovery_category_adjustment(tags, list(topic_keys))
    except Exception:
        pass
    try:
        from bot.editorial.flow_health.longtail import longtail_coverage_adjustment

        longtail_boost = longtail_coverage_adjustment(tags)
    except Exception:
        pass

    raw = (
        factors.source_trust * 0.1
        + factors.storyline_importance * 0.12
        + factors.novelty * 0.14
        + factors.market_impact * 0.1
        + factors.geopolitical_impact * 0.1
        + factors.entity_significance * 0.1
        + factors.topic_momentum * 0.1
        + factors.cross_source_confirmation * 0.12
        + factors.editorial_quality * 0.12
        - factors.audience_fatigue * 0.12
        - factors.topic_balance_penalty
        + category_recovery_boost
        + longtail_boost
    )
    if detect_shallow_rewrite(headline, summary):
        raw -= 0.12

    score = round(_clamp(raw), 3)
    is_dup = follow_up_kind in ("duplicate", "minor_variation")
    urgency = classify_urgency(
        editorial_priority_score=score,
        momentum=topic_momentum,
        novelty=novelty,
        market_impact=market,
        geopolitical_impact=geo,
        is_duplicate_follow_up=is_dup,
    )

    warnings = build_noise_warnings(
        editorial_priority_score=score,
        information_density=information_density,
        follow_up_kind=follow_up_kind,
        match_score=memory_match_score,
        momentum=topic_momentum,
    )

    why: list[str] = []
    if factors.cross_source_confirmation >= 0.65:
        why.append("multi-source corroboration")
    if factors.entity_significance >= 0.85:
        why.append(f"high-signal entities ({', '.join(entity_hits[:3])})")
    if factors.topic_momentum >= 0.55:
        why.append(f"storyline momentum: {momentum.get('momentum_label', 'building')}")
    if factors.geopolitical_impact >= 0.7:
        why.append("geopolitical significance")
    if factors.market_impact >= 0.7:
        why.append("market impact")
    if factors.novelty >= 0.65:
        why.append("high novelty")
    if factors.audience_fatigue >= 0.55:
        why.append("audience fatigue penalty applied")
    if not why and score >= 0.5:
        why.append("balanced editorial signals")

    return EditorialPriorityResult(
        editorial_priority_score=score,
        urgency_class=urgency,
        factors=factors,
        warnings=warnings,
        momentum=momentum,
        balance=balance,
        why_ranked=tuple(why[:5]),
        entity_hits=tuple(entity_hits),
    )
