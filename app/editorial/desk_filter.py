"""Editorial desk filter — final gate before draft generation (Reuters-style triage)."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from app.editorial.desk_starvation import DeskThresholdContext, desk_threshold_context, record_desk_decision
from app.editorial.desk_thresholds import category_min_publish_score
from app.editorial.scoring_engine import EditorialScore

logger = logging.getLogger(__name__)

# --- Noise / reject patterns (deterministic) ---
_MEME_NOISE = re.compile(
    r"(мем|лол|rofl|haha|😂|🤣|прикол|шутк|funny|lol\b|meme\b)",
    re.I,
)
_INCIDENT_NOISE = re.compile(
    r"(подрядчик|отправил\s+картин|wrong\s+image|перепутал\s+фото|опечатк[аи].*картин)",
    re.I,
)
_HYPE_NOISE = re.compile(
    r"(to\s+the\s+moon|100x|гарантированн|pump\s+soon|не\s+финансов.*совет|not\s+financial\s+advice)",
    re.I,
)
_MARKETING = re.compile(
    r"(подписывайтесь|subscribe\s+now|реклам|sponsored|промокод|giveaway)",
    re.I,
)
_CLICKBAIT = re.compile(
    r"(срочно\s+узнай|шокирующ|you\s+won't\s+believe|это\s+изменит\s+всё)",
    re.I,
)
_UNVERIFIED = re.compile(
    r"(по\s+слухам|unconfirmed|слухи|insider\s+says|якобы\s+без\s+подтвержд)",
    re.I,
)
_UNSAFE_PUBLIC_TOPIC = re.compile(
    r"(проститут|эскорт|sex\s*work|adult\s*services|порно|pornhub|onlyfans|"
    r"tabloid\s+scandal|жёлтая\s+пресса|outrage\s+bait|gossip\s+column|"
    r"интим[-\s]?услуг|секс[-\s]?работ)",
    re.I,
)
_TABLOID_BAIT = re.compile(
    r"(шокирующ|срочно\s+узнай|вы\s+не\s+поверите|это\s+изменит\s+всё|"
    r"you\s+won't\s+believe|gone\s+wild)",
    re.I,
)
_BUREAUCRATIC_FILLER = re.compile(
    r"(приказ(ом)?|утвержден(а|о|ы)?\s+форма|предписани|в\s+соответствии\s+с|"
    r"регламент|процедур|территори(и|я)\s+российской)",
    re.I,
)
_IMPLICATION_SIGNAL = re.compile(
    r"(это\s+значит|влиян|давлен|риск|издержк|ликвидност|доходност|волатильн|"
    r"логистик|экспорт|импорт|рынк)",
    re.I,
)

_MACRO = re.compile(
    r"(росстат|инфляц|дефляц|ввп|gdp|cpi|ppi|цб\s|фрс|fed\b|ecb|ключев.*ставк|"
    r"central\s+bank|минюст|санкци|таможн|тариф|budget|фискал|экономик)",
    re.I,
)
_MARKET = re.compile(
    r"(биткоин|bitcoin|btc\b|крипт|crypto|бирж|exchange|хак|hack|defi|"
    r"ethereum|eth\b|moscow\s+exchange|мосбирж|стейбл)",
    re.I,
)
_BREAKING_KW = re.compile(
    r"\b(breaking|urgent|just\s+in|экстренно|срочно|взрыв|attack|resignation|war\s+escalation)\b",
    re.I,
)

_BREAKING_OVERRIDE_SCORE = float(os.getenv("DESK_BREAKING_OVERRIDE_SCORE", "0.75"))
_URGENCY_OVERRIDE = float(os.getenv("DESK_URGENCY_OVERRIDE", "0.8"))


@dataclass(frozen=True)
class DeskDecision:
    publish: bool
    reason: str
    editorial_category: str  # macro | market | breaking | noise | reject
    quality_score: float
    priority_tier: str  # priority | lower | reject
    breaking_override: bool = False
    threshold_used: float = 0.0
    reason_code: str = ""
    manual_review_required: bool = False
    signal_score: float = 0.0
    score_breakdown: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clarity_score(text: str) -> float:
    t = (text or "").strip()
    if len(t) < 40:
        return 0.2
    sentences = [s for s in re.split(r"[.!?\n]+", t) if len(s.strip()) > 12]
    if len(sentences) < 2:
        return 0.35
    avg_len = sum(len(s) for s in sentences) / len(sentences)
    if 40 <= avg_len <= 280:
        return 0.85
    return 0.55


def _novelty_score(text: str) -> float:
    words = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9]{4,}", (text or "").lower())
    if len(words) < 8:
        return 0.25
    unique_ratio = len(set(words)) / len(words)
    return round(min(1.0, 0.3 + 0.7 * unique_ratio), 4)


def _detect_category(text: str, escore: EditorialScore) -> str:
    t = text or ""
    if _MEME_NOISE.search(t) or _INCIDENT_NOISE.search(t):
        return "noise"
    if escore.is_breaking or escore.breaking_score >= 0.7 or _BREAKING_KW.search(t):
        return "breaking"
    if _MACRO.search(t):
        return "macro"
    if _MARKET.search(t):
        return "market"
    if escore.relevance_score < 0.25:
        return "reject"
    return "market" if escore.impact_score < 0.35 else "macro"


def _quality_score(escore: EditorialScore, text: str) -> float:
    cred = escore.credibility_score
    impact = escore.impact_score
    clarity = _clarity_score(text)
    novelty = _novelty_score(text)
    return round((cred * 0.35 + impact * 0.35 + clarity * 0.15 + novelty * 0.15) * 100, 2)


def _score_breakdown(escore: EditorialScore, text: str, *, category: str, ctx: DeskThresholdContext) -> dict[str, Any]:
    clarity = _clarity_score(text)
    novelty = _novelty_score(text)
    q = _quality_score(escore, text)
    return {
        "quality_score": q,
        "components": {
            "credibility": round(escore.credibility_score, 4),
            "impact": round(escore.impact_score, 4),
            "clarity": round(clarity, 4),
            "novelty": round(novelty, 4),
            "relevance": round(escore.relevance_score, 4),
            "urgency": round(escore.urgency_score, 4),
            "final_priority_score": escore.final_priority_score,
        },
        "weights": {"credibility": 0.35, "impact": 0.35, "clarity": 0.15, "novelty": 0.15},
        "editorial_category": category,
        "threshold_used": ctx.effective_min_publish_score,
        "relevance_floor": ctx.relevance_floor,
        "starvation_recovery_active": ctx.starvation_active,
    }


def _log_desk_decision(
    decision: DeskDecision,
    *,
    escore: EditorialScore,
    sources: list[str],
) -> None:
    try:
        from utils.structured_log import log_event

        log_event(
            logger,
            "desk.decision",
            publish=decision.publish,
            reason=decision.reason,
            reason_code=decision.reason_code or None,
            editorial_category=decision.editorial_category,
            quality_score=decision.quality_score,
            priority_tier=decision.priority_tier,
            breaking_override=decision.breaking_override,
            threshold_used=decision.threshold_used,
            score_breakdown=decision.score_breakdown,
            sources=sources[:5],
            editorial_lane=escore.lane,
        )
    except Exception:
        pass


def _hard_content_violation(text: str) -> str | None:
    """Safety rejects that must never be bypassed (debug/recovery/starvation)."""
    from app.editorial.content_quality import has_hidden_advertising, is_incomplete_teaser

    if has_hidden_advertising(text or ""):
        return "hidden_advertising_or_native_ad"
    if is_incomplete_teaser(text or ""):
        return "incomplete_teaser_no_body"
    return None


def evaluate_desk_filter(
    text: str,
    escore: EditorialScore,
    *,
    sources: list[str] | None = None,
    runtime_dir: str | None = None,
    bypass: bool = False,
    threshold_ctx: DeskThresholdContext | None = None,
) -> DeskDecision:
    """
    Final editorial desk decision before draft generation.
    """
    sources = list(sources or [])
    unique_sources = len(set(sources))
    ctx = threshold_ctx or desk_threshold_context()
    q = _quality_score(escore, text)
    category = _detect_category(text, escore)
    breakdown = _score_breakdown(escore, text, category=category, ctx=ctx)
    breaking_override = (
        escore.breaking_score > _BREAKING_OVERRIDE_SCORE
        or escore.urgency_score > _URGENCY_OVERRIDE
    ) and not _MEME_NOISE.search(text or "")

    def _finish(decision: DeskDecision) -> DeskDecision:
        _log_desk_decision(decision, escore=escore, sources=sources)
        record_desk_decision(
            runtime_dir,
            publish=decision.publish,
            reason=decision.reason,
            quality_score=q,
            threshold_ctx=ctx,
        )
        return decision

    hard = _hard_content_violation(text or "")
    if hard:
        return _finish(
            _reject(hard, "reject", q, ctx, breakdown, runtime_dir=runtime_dir)
        )

    if bypass:
        decision = DeskDecision(
            publish=True,
            reason="debug_bypass",
            editorial_category=category,
            quality_score=q,
            priority_tier="priority",
            breaking_override=breaking_override,
            threshold_used=ctx.effective_min_publish_score,
            manual_review_required=False,
            signal_score=0.0,
            score_breakdown=breakdown,
        )
        _log_desk_decision(decision, escore=escore, sources=sources)
        record_desk_decision(runtime_dir, publish=True, reason=decision.reason, quality_score=q, threshold_ctx=ctx)
        return decision

    min_publish = category_min_publish_score(category, ctx)
    breakdown["threshold_used"] = min_publish
    lower = ctx.lower_priority_score
    macro_floor = ctx.min_macro_market_score
    rel_floor = ctx.relevance_floor

    # Hard rejects
    if _MEME_NOISE.search(text or "") and not breaking_override:
        return _finish(_reject("meme_or_joke_content", "noise", q, ctx, breakdown, runtime_dir=runtime_dir))
    if _INCIDENT_NOISE.search(text or ""):
        return _finish(_reject("low_value_incident", "noise", q, ctx, breakdown, runtime_dir=runtime_dir))
    if _MARKETING.search(text or ""):
        return _finish(_reject("marketing_or_promo", "noise", q, ctx, breakdown, runtime_dir=runtime_dir))
    if _HYPE_NOISE.search(text or "") and escore.impact_score < 0.45:
        return _finish(_reject("crypto_hype_without_substance", "reject", q, ctx, breakdown, runtime_dir=runtime_dir))
    if _CLICKBAIT.search(text or "") and escore.credibility_score < 0.65:
        return _finish(_reject("clickbait_unverified_framing", "reject", q, ctx, breakdown, runtime_dir=runtime_dir))
    if _UNVERIFIED.search(text or "") and unique_sources < 2 and not breaking_override:
        return _finish(_reject("single_source_unverified", "reject", q, ctx, breakdown, runtime_dir=runtime_dir))
    from app.editorial.source_languages import LANG_ZH, detect_text_language, language_for_channel

    min_text_len = 35
    if any(language_for_channel(s) == LANG_ZH for s in sources) or detect_text_language(text or "") == LANG_ZH:
        min_text_len = 12
    if len((text or "").strip()) < min_text_len:
        return _finish(_reject("low_information_density", "noise", q, ctx, breakdown, runtime_dir=runtime_dir))
    if _UNSAFE_PUBLIC_TOPIC.search(text or ""):
        return _finish(_reject("unsafe_public_topic", "reject", q, ctx, breakdown, runtime_dir=runtime_dir))
    if _TABLOID_BAIT.search(text or "") and escore.credibility_score < 0.72:
        return _finish(_reject("tabloid_bait_framing", "reject", q, ctx, breakdown, runtime_dir=runtime_dir))
    if _BUREAUCRATIC_FILLER.search(text or "") and not _IMPLICATION_SIGNAL.search(text or ""):
        return _finish(
            _reject("bureaucratic_filler_low_signal", "reject", q, ctx, breakdown, runtime_dir=runtime_dir)
        )

    from app.editorial.governance_advanced import evaluate_advanced_governance

    gov = evaluate_advanced_governance(text or "")
    if gov.auto_block:
        return _finish(_reject(f"governance_{gov.reason}", "reject", q, ctx, breakdown, runtime_dir=runtime_dir))

    from app.editorial.signal_ranking import rank_story_signal
    from app.editorial.source_tiers import aggregate_source_tier

    signal = rank_story_signal(
        text,
        escore,
        sources=sources,
        runtime_dir=runtime_dir,
        category=category,
        clarity=_clarity_score(text),
    )
    breakdown["signal_ranking"] = signal.to_dict()
    tier_info = aggregate_source_tier(sources, runtime_dir=runtime_dir)
    breakdown["source_tier"] = tier_info.to_dict()

    if signal.reject_reason and not breaking_override:
        return _finish(
            _reject(
                str(signal.reject_reason),
                "reject",
                q,
                ctx,
                breakdown,
                runtime_dir=runtime_dir,
                signal_score=signal.signal_score,
            )
        )
    if tier_info.tier >= 3 and q < min_publish + 5 and not breaking_override and unique_sources < 2:
        return _finish(
            _reject(
                "low_authority_single_source",
                "reject",
                q,
                ctx,
                breakdown,
                runtime_dir=runtime_dir,
                signal_score=signal.signal_score,
            )
        )

    manual_review = signal.manual_review_hint

    if breaking_override:
        _record_metrics(runtime_dir, decision="include", breaking_override=True, q=q)
        return _finish(
            DeskDecision(
                publish=True,
                reason="breaking_override",
                editorial_category="breaking",
                quality_score=q,
                priority_tier="priority",
                breaking_override=True,
                threshold_used=min_publish,
                manual_review_required=manual_review,
                signal_score=signal.signal_score,
                score_breakdown=breakdown,
            )
        )

    if category == "noise":
        return _finish(_reject("classified_noise", "noise", q, ctx, breakdown, runtime_dir=runtime_dir))

    def _macro_market_floor_ok() -> bool:
        return (
            category in {"macro", "market"}
            and q >= macro_floor
            and escore.relevance_score >= 0.22
        )

    if q >= min_publish or category in {"macro", "breaking"}:
        tier = "priority"
        reason = "desk_priority_include"
        if category == "macro" and q >= 65:
            reason = "macro_high_signal"
        publish = True
    elif q >= lower:
        tier = "lower"
        reason = "desk_lower_priority_allow"
        publish = category in {"macro", "market"} and escore.relevance_score >= rel_floor
        if not publish and _macro_market_floor_ok():
            publish = True
            reason = "desk_macro_market_floor"
        elif not publish:
            return _finish(
                _reject("below_priority_threshold", category, q, ctx, breakdown, runtime_dir=runtime_dir)
            )
    elif _macro_market_floor_ok():
        tier = "lower"
        reason = "desk_macro_market_floor"
        publish = True
    else:
        return _finish(_reject("quality_below_threshold", "reject", q, ctx, breakdown, runtime_dir=runtime_dir))

    _record_metrics(runtime_dir, decision="include", breaking_override=False, q=q)
    return _finish(
        DeskDecision(
            publish=publish,
            reason=reason,
            editorial_category=category,
            quality_score=q,
            priority_tier=tier,
            breaking_override=False,
            threshold_used=min_publish,
            manual_review_required=manual_review,
            signal_score=signal.signal_score,
            score_breakdown=breakdown,
        )
    )


def _desk_reason_code(reason: str, category: str) -> str:
    cat = (category or "reject").strip().lower()
    if cat == "noise":
        prefix = "desk.noise"
    elif cat in {"macro", "market", "breaking"}:
        prefix = f"desk.{cat}"
    else:
        prefix = "desk.reject"
    mapping = {
        "meme_or_joke_content": f"{prefix}.meme_or_joke",
        "low_value_incident": f"{prefix}.low_value_incident",
        "marketing_or_promo": f"{prefix}.marketing",
        "crypto_hype_without_substance": "desk.reject.crypto_hype",
        "clickbait_unverified_framing": "desk.reject.clickbait",
        "single_source_unverified": "desk.reject.unverified_single_source",
        "low_information_density": f"{prefix}.low_density",
        "classified_noise": f"{prefix}.classified_noise",
        "below_priority_threshold": f"{prefix}.below_priority_threshold",
        "quality_below_threshold": f"{prefix}.quality_below_threshold",
        "unsafe_public_topic": "desk.reject.unsafe_public_topic",
        "tabloid_bait_framing": "desk.reject.tabloid_bait",
        "signal_below_threshold": "desk.reject.low_signal",
        "meme_economics": "desk.reject.meme_economics",
        "gossip_low_authority": "desk.reject.gossip",
        "sensationalism_low_authority": "desk.reject.sensationalism",
        "low_authority_single_source": "desk.reject.low_authority_source",
        "incomplete_teaser_no_body": "desk.noise.incomplete_teaser",
        "bureaucratic_filler_low_signal": "desk.reject.bureaucratic_filler",
        "hidden_advertising_or_native_ad": "desk.reject.hidden_advertising",
    }
    return mapping.get(reason, f"{prefix}.{reason}")


def _reject(
    reason: str,
    category: str,
    q: float,
    ctx: DeskThresholdContext,
    breakdown: dict[str, Any],
    *,
    runtime_dir: str | None = None,
    signal_score: float = 0.0,
) -> DeskDecision:
    _record_metrics(runtime_dir, decision="reject", breaking_override=False, q=q)
    return DeskDecision(
        publish=False,
        reason=reason,
        reason_code=_desk_reason_code(reason, category),
        editorial_category=category if category != "macro" else "reject",
        quality_score=q,
        priority_tier="reject",
        breaking_override=False,
        threshold_used=breakdown.get("threshold_used") or ctx.effective_min_publish_score,
        manual_review_required=False,
        signal_score=signal_score,
        score_breakdown=breakdown,
    )


def persist_rejection(
    runtime_dir: str | None,
    *,
    article_id: str,
    text_preview: str,
    decision: DeskDecision,
    sources: list[str],
    escore: EditorialScore | None = None,
) -> None:
    from ops.pipeline.paths import runtime_root

    row = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "article_id": article_id,
        "sources": sources,
        "text_preview": (text_preview or "")[:500],
        "desk": decision.to_dict(),
        "scores": escore.to_dict() if escore else {},
    }
    path = runtime_root(runtime_dir) / "rejected_items.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def _record_metrics(runtime_dir: str | None, *, decision: str, breaking_override: bool, q: float) -> None:
    try:
        from utils.metrics import inc, set_gauge

        if decision == "include":
            inc("desk_included_items_total")
            if breaking_override:
                inc("desk_breaking_override_count")
        elif decision == "reject":
            inc("desk_rejected_items_total")
        inc("desk_scoring_total")
        set_gauge("desk_avg_quality_score", q)
    except Exception:
        pass


def desk_metrics_snapshot() -> dict[str, Any]:
    from utils.metrics import export_snapshot

    c = export_snapshot().get("counters") or {}
    rejected = int(c.get("desk_rejected_items_total", 0))
    included = int(c.get("desk_included_items_total", 0))
    total = rejected + included
    snap = {
        "rejected_items_total": rejected,
        "included_items_total": included,
        "rejection_rate": round(rejected / total, 4) if total else 0.0,
        "included_vs_rejected_ratio": round(included / max(1, rejected), 4),
        "breaking_override_count": int(c.get("desk_breaking_override_count", 0)),
        "avg_quality_score": c.get("desk_avg_quality_score"),
    }
    try:
        snap.update(desk_health_snapshot())
    except Exception:
        pass
    return snap


def desk_health_snapshot() -> dict[str, Any]:
    from app.editorial.desk_starvation import desk_health_snapshot as _snap

    return _snap()
