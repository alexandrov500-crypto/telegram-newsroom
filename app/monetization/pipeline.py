"""W5 monetization pre/post publish pipeline."""

from __future__ import annotations

import os
from dataclasses import dataclass

from app.monetization.ad_inventory import allocate_ad_slot
from app.monetization.audience_value import score_audience_value
from app.monetization.conversion_funnel import insert_conversion_cta, pick_funnel_cta, record_conversion_event
from app.monetization.financial_feedback import load_topic_roi_weights_sync, profitability_boost
from app.monetization.monetization_balance import can_inject_sponsor, evaluate_monetization_stress, record_publish_type
from app.monetization.premium_layer import classify_premium_content, split_free_premium_body
from app.monetization.revenue_engine import (
    RevenueStream,
    route_revenue_stream,
    score_monetization_eligibility,
)
from app.monetization.sponsor_injection import inject_sponsor_block, pick_sponsor_slot, score_sponsor_safety


@dataclass(frozen=True)
class MonetizationEnrichment:
    content: str
    premium_free_body: str
    premium_body: str
    is_premium: bool
    sponsor_injected: bool
    revenue_stream: str
    eligibility_score: float


@dataclass(frozen=True)
class MonetizationPrePublishVerdict:
    allowed: bool
    reason: str
    stress_score: float
    revenue_stream: str
    eligibility_score: float


def _enabled() -> bool:
    return os.getenv("W5_MONETIZATION_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")


async def enrich_with_monetization(
    body: str,
    *,
    vertical: str = "general",
    insight_score: float = 0.0,
    style_score: float = 0.0,
    signal_score: float = 0.55,
    runtime_dir: str = "",
    newsroom_tz: str = "Europe/Moscow",
    narrative_phase: str = "developing",
) -> MonetizationEnrichment:
    if not _enabled():
        return MonetizationEnrichment(body, body, "", False, False, "organic", 0.0)

    elig = score_monetization_eligibility(
        body,
        vertical=vertical,
        insight_score=insight_score,
        style_score=style_score,
        signal_score=signal_score,
    )
    routing = route_revenue_stream(elig)
    text = body

    premium_cls = classify_premium_content(text, insight_score=insight_score, vertical=vertical)
    free_body, premium_body = split_free_premium_body(text, premium_cls)

    profile = score_audience_value(topic_bucket=vertical, runtime_dir=runtime_dir)
    cta = pick_funnel_cta(profile)
    if cta and not premium_cls.is_premium:
        text = insert_conversion_cta(text, cta)
        try:
            await record_conversion_event(
                event_type="cta_inserted",
                funnel_stage=cta.stage,
                cohort=profile.cohort,
                value_score=profile.ltv_score,
            )
        except Exception:
            pass

    sponsor_injected = False
    if (
        RevenueStream.SPONSORED in elig.streams
        and can_inject_sponsor(runtime_dir)
        and score_sponsor_safety(text, vertical=vertical) >= float(os.getenv("W5_SPONSOR_MIN_SAFETY", "0.62"))
    ):
        slot_decision = allocate_ad_slot(
            runtime_dir=runtime_dir,
            topic_bucket=vertical,
            narrative_phase=narrative_phase,
            newsroom_tz=newsroom_tz,
            audience_mood=profile.ltv_score,
        )
        if slot_decision.allocate:
            slot = await pick_sponsor_slot(vertical=vertical)
            inj = inject_sponsor_block(text, slot=slot, vertical=vertical)
            if inj.injected:
                text = inj.content
                sponsor_injected = True
                if slot:
                    from app.monetization.sponsor_injection import record_sponsor_use

                    await record_sponsor_use(slot.slot_key)

    if premium_cls.is_premium:
        text = free_body

    return MonetizationEnrichment(
        content=text,
        premium_free_body=free_body,
        premium_body=premium_body,
        is_premium=premium_cls.is_premium,
        sponsor_injected=sponsor_injected,
        revenue_stream=routing.stream.value,
        eligibility_score=elig.score,
    )


async def evaluate_monetization_pre_publish(
    *,
    runtime_dir: str,
    vertical: str = "general",
    is_breaking: bool = False,
    operator_override: bool = False,
    sponsor_intent: bool = False,
) -> MonetizationPrePublishVerdict:
    if not _enabled() or is_breaking or operator_override:
        return MonetizationPrePublishVerdict(True, "exempt", 0.0, "organic", 0.0)

    balance = evaluate_monetization_stress(runtime_dir)
    if sponsor_intent and not balance.allowed:
        return MonetizationPrePublishVerdict(
            False,
            balance.reason,
            balance.stress_score,
            "sponsored",
            0.0,
        )

    roi_weights = load_topic_roi_weights_sync(runtime_dir)
    boost = profitability_boost(vertical, roi_weights)

    return MonetizationPrePublishVerdict(True, "ok", balance.stress_score, "organic", boost)


def record_monetized_publish(runtime_dir: str, *, sponsor_injected: bool, is_premium: bool) -> None:
    if sponsor_injected:
        record_publish_type(runtime_dir, "sponsored")
    elif is_premium:
        record_publish_type(runtime_dir, "premium")
    else:
        record_publish_type(runtime_dir, "editorial")
