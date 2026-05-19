from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

RISK_AUTO_APPROVE_MAX = 0.35
CONFIDENCE_AUTO_APPROVE_MIN = 0.72
BREAKING_PRIORITY_MIN = 0.85
TRUST_AUTO_APPROVE_MIN = 0.62
CORROBORATION_MIN_SOURCES = 2
ENTITY_CONFIDENCE_MIN = 1

_BLOCK_POLITICAL_MISINFO = "political_misinformation"
_BLOCK_MEDICAL_MISINFO = "medical_misinformation"
_BLOCK_FINANCIAL_RUMOR = "unverified_financial_rumor"
_BLOCK_VIOLENT_GRAPHIC = "violent_graphic"
_BLOCK_LOW_CONFIDENCE_BREAKING = "low_confidence_breaking"

_NEVER_AUTO_APPROVE: frozenset[str] = frozenset(
    {
        _BLOCK_POLITICAL_MISINFO,
        _BLOCK_MEDICAL_MISINFO,
        _BLOCK_FINANCIAL_RUMOR,
        _BLOCK_VIOLENT_GRAPHIC,
        _BLOCK_LOW_CONFIDENCE_BREAKING,
    }
)

_POLITICAL_RE = re.compile(
    r"\b(election|ballot|campaign|partisan|impeach|propaganda|deep\s*state)\b",
    re.I,
)
_MEDICAL_RE = re.compile(
    r"\b(cure|miracle\s+treatment|anti-?vax|vaccine\s+hoax|ivermectin\s+cures)\b",
    re.I,
)
_FINANCIAL_RUMOR_RE = re.compile(
    r"\b(rumor|rumour|unverified\s+tip|insider\s+tip|pump\s+and\s+dump|"
    r"guaranteed\s+returns|price\s+target\s+leak)\b",
    re.I,
)
_VIOLENCE_RE = re.compile(
    r"\b(mass\s+shooting|beheading|graphic\s+violence|gore)\b",
    re.I,
)
_DISASTER_RE = re.compile(
    r"\b(earthquake|tsunami|wildfire|mass\s+casualt|death\s+toll)\b",
    re.I,
)
_SECURITY_RE = re.compile(
    r"\b(hack|breach|ransomware|zero-?day|exploit|cyberattack)\b",
    re.I,
)
_BREAKING_RE = re.compile(
    r"\b(breaking|urgent|just\s+in|developing)\b",
    re.I,
)


@dataclass(frozen=True, slots=True)
class StoryAgentContext:
    pending_news_id: int
    title: str
    summary: str | None
    tags: list[str]
    source: str | None
    source_count: int
    priority_score: float
    source_trust: float
    source_approval_ratio: float
    entity_names: list[str] = field(default_factory=list)
    cluster_variant_count: int = 1
    topic_virality: float = 0.5
    adaptive_hook_score: float | None = None


@dataclass(frozen=True, slots=True)
class RiskAssessment:
    risk_score: float
    risk_factors: tuple[str, ...]
    blocked_categories: tuple[str, ...]
    requires_human_review: bool
    publish_confidence: float = 0.5


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _text_blob(ctx: StoryAgentContext) -> str:
    return f"{ctx.title} {ctx.summary or ''} {' '.join(ctx.tags)}".lower()


def _detect_blocked_categories(ctx: StoryAgentContext) -> list[str]:
    blocked: list[str] = []
    text = _text_blob(ctx)
    if _POLITICAL_RE.search(text) and ctx.source_count < CORROBORATION_MIN_SOURCES:
        blocked.append(_BLOCK_POLITICAL_MISINFO)
    if _MEDICAL_RE.search(text):
        blocked.append(_BLOCK_MEDICAL_MISINFO)
    if _FINANCIAL_RUMOR_RE.search(text):
        blocked.append(_BLOCK_FINANCIAL_RUMOR)
    if _VIOLENCE_RE.search(text):
        blocked.append(_BLOCK_VIOLENT_GRAPHIC)
    if _BREAKING_RE.search(text) and (
        ctx.source_count < CORROBORATION_MIN_SOURCES or ctx.source_trust < TRUST_AUTO_APPROVE_MIN
    ):
        blocked.append(_BLOCK_LOW_CONFIDENCE_BREAKING)
    return blocked


def evaluate_story_risk(ctx: StoryAgentContext) -> RiskAssessment:
    """Compute editorial risk score and guardrail flags. Never raises."""
    factors: list[str] = []
    score = 0.12
    text = _text_blob(ctx)

    if ctx.source_trust < 0.45:
        factors.append("low_trust_source")
        score += 0.28
    elif ctx.source_trust < TRUST_AUTO_APPROVE_MIN:
        factors.append("moderate_trust_source")
        score += 0.12

    if ctx.source_count < CORROBORATION_MIN_SOURCES:
        factors.append("missing_corroboration")
        score += 0.22
    elif ctx.source_count >= 3:
        score -= 0.08

    if ctx.source_count >= 2 and ctx.priority_score < 0.55:
        factors.append("conflicting_reports")
        score += 0.18

    if len(ctx.entity_names) < ENTITY_CONFIDENCE_MIN:
        factors.append("low_entity_confidence")
        score += 0.14

    if _POLITICAL_RE.search(text):
        factors.append("political_topic")
        score += 0.16

    if _DISASTER_RE.search(text) or _VIOLENCE_RE.search(text):
        factors.append("violence_or_disaster")
        score += 0.20

    if _FINANCIAL_RUMOR_RE.search(text):
        factors.append("financial_rumor_language")
        score += 0.24

    if _SECURITY_RE.search(text):
        factors.append("security_incident")
        score += 0.10

    blocked = _detect_blocked_categories(ctx)
    for category in blocked:
        score = max(score, 0.72)

    risk_score = _clamp(score)
    confidence = evaluate_publish_confidence(ctx, risk_score=risk_score, blocked=blocked)
    requires_human = bool(blocked) or risk_score > RISK_AUTO_APPROVE_MAX

    if requires_human:
        logger.info(
            "event=risk_review_required pending_news_id=%d risk=%.3f factors=%r blocked=%r",
            ctx.pending_news_id,
            risk_score,
            factors,
            blocked,
        )

    return RiskAssessment(
        risk_score=risk_score,
        risk_factors=tuple(factors),
        blocked_categories=tuple(blocked),
        requires_human_review=requires_human,
        publish_confidence=confidence,
    )


def evaluate_publish_confidence(
    ctx: StoryAgentContext,
    *,
    risk_score: float | None = None,
    blocked: list[str] | None = None,
) -> float:
    """Estimate confidence that auto-publish is appropriate (0–1)."""
    blocked = blocked if blocked is not None else _detect_blocked_categories(ctx)
    if blocked:
        return 0.15

    confidence = 0.45
    confidence += min(0.22, ctx.priority_score * 0.22)
    confidence += min(0.15, (ctx.source_trust - 0.5) * 0.35)
    confidence += min(0.12, max(0, ctx.source_count - 1) * 0.06)
    confidence += min(0.08, len(ctx.entity_names) * 0.03)
    confidence += min(0.06, (ctx.topic_virality - 0.5) * 0.15)
    confidence += min(0.05, max(0.0, ctx.source_approval_ratio - 0.5) * 0.12)

    if risk_score is None:
        risk_score = evaluate_story_risk(ctx).risk_score
    confidence -= risk_score * 0.35

    if ctx.cluster_variant_count >= CORROBORATION_MIN_SOURCES:
        confidence += 0.05

    return _clamp(confidence)


def should_auto_approve(
    ctx: StoryAgentContext,
    assessment: RiskAssessment,
    *,
    auto_approval_enabled: bool,
) -> bool:
    """Fail-closed auto-approval gate."""
    if not auto_approval_enabled:
        return False
    if runtime_state_blocks(assessment):
        return False
    if assessment.requires_human_review:
        return False
    if assessment.risk_score > RISK_AUTO_APPROVE_MAX:
        return False
    min_sources = CORROBORATION_MIN_SOURCES
    min_entities = ENTITY_CONFIDENCE_MIN
    conf_min = CONFIDENCE_AUTO_APPROVE_MIN
    try:
        from bot.editorial.flow_health.floor import should_relax_auto_approval

        if should_relax_auto_approval():
            min_sources = 1
            min_entities = 0
            conf_min = max(0.62, CONFIDENCE_AUTO_APPROVE_MIN - 0.08)
    except Exception:
        pass
    if assessment.publish_confidence < conf_min:
        return False
    if ctx.source_trust < TRUST_AUTO_APPROVE_MIN:
        return False
    if ctx.source_count < min_sources:
        return False
    if len(ctx.entity_names) < min_entities:
        return False
    sensitive_tags = {"politics", "election", "health", "medical", "rumor", "gossip"}
    if sensitive_tags.intersection(tag.lower() for tag in ctx.tags):
        return False
    return True


def runtime_state_blocks(assessment: RiskAssessment) -> bool:
    return bool(set(assessment.blocked_categories) & _NEVER_AUTO_APPROVE)


def should_trigger_breaking_alert(
    ctx: StoryAgentContext,
    assessment: RiskAssessment,
) -> bool:
    """Detect stories that warrant a breaking-news signal."""
    if runtime_state_blocks(assessment):
        return False
    text = _text_blob(ctx)
    sudden_spike = ctx.priority_score >= BREAKING_PRIORITY_MIN and ctx.source_count >= 2
    trusted_convergence = (
        ctx.source_count >= 3
        and ctx.source_trust >= TRUST_AUTO_APPROVE_MIN
        and ctx.priority_score >= 0.75
    )
    security = _SECURITY_RE.search(text) is not None and ctx.priority_score >= 0.7
    major_ai = (
        any(name.lower() in ("openai", "anthropic", "google", "microsoft") for name in ctx.entity_names)
        and ctx.priority_score >= 0.72
    )
    explicit_breaking = _BREAKING_RE.search(text) is not None and ctx.source_count >= 2

    if sudden_spike or trusted_convergence or security or major_ai or explicit_breaking:
        logger.info(
            "event=breaking_alert_triggered pending_news_id=%d priority=%.2f sources=%d",
            ctx.pending_news_id,
            ctx.priority_score,
            ctx.source_count,
        )
        return True
    return False


def breaking_headline_prefix() -> str:
    return "🚨 Breaking News"
