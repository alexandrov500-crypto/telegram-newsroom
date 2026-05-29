"""Revenue routing engine — multi-stream monetization eligibility."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum


class RevenueStream(str, Enum):
    ORGANIC = "organic"
    SPONSORED = "sponsored"
    PREMIUM = "premium"
    B2B_API = "b2b_api"
    SYNDICATION = "syndication"
    DATA_LICENSE = "data_license"


@dataclass(frozen=True)
class MonetizationEligibility:
    score: float
    streams: tuple[RevenueStream, ...]
    primary_stream: RevenueStream
    sponsor_safe: bool
    premium_candidate: bool
    syndication_eligible: bool
    reason: str


@dataclass(frozen=True)
class RevenueRoutingDecision:
    stream: RevenueStream
    estimated_cpm_usd: float
    eligibility: MonetizationEligibility


def _enabled() -> bool:
    return os.getenv("W5_REVENUE_ENGINE_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")


def score_monetization_eligibility(
    content: str,
    *,
    vertical: str = "general",
    insight_score: float = 0.0,
    style_score: float = 0.0,
    signal_score: float = 0.55,
    is_breaking: bool = False,
) -> MonetizationEligibility:
    if not _enabled():
        return MonetizationEligibility(0.0, (RevenueStream.ORGANIC,), RevenueStream.ORGANIC, True, False, False, "disabled")

    score = 0.25 * signal_score + 0.25 * insight_score + 0.20 * style_score
    streams: list[RevenueStream] = [RevenueStream.ORGANIC]

    sponsor_safe = style_score >= 0.58 and insight_score >= 0.45 and not is_breaking
    if sponsor_safe and score >= 0.52:
        streams.append(RevenueStream.SPONSORED)

    premium_candidate = insight_score >= 0.72 and style_score >= 0.65 and len(content or "") >= 320
    if premium_candidate:
        streams.append(RevenueStream.PREMIUM)

    syndication_eligible = insight_score >= 0.68 and style_score >= 0.62
    if syndication_eligible:
        streams.append(RevenueStream.SYNDICATION)
        if os.getenv("W5_B2B_API_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on"):
            streams.append(RevenueStream.B2B_API)

    if vertical in ("macro", "finance", "crypto") and score >= 0.6:
        streams.append(RevenueStream.DATA_LICENSE)

    primary = RevenueStream.ORGANIC
    if RevenueStream.PREMIUM in streams and insight_score >= 0.78:
        primary = RevenueStream.PREMIUM
    elif RevenueStream.SPONSORED in streams and score >= 0.55:
        primary = RevenueStream.SPONSORED
    elif RevenueStream.SYNDICATION in streams:
        primary = RevenueStream.SYNDICATION

    return MonetizationEligibility(
        score=round(min(1.0, score), 4),
        streams=tuple(dict.fromkeys(streams)),
        primary_stream=primary,
        sponsor_safe=sponsor_safe,
        premium_candidate=premium_candidate,
        syndication_eligible=syndication_eligible,
        reason="ok",
    )


def route_revenue_stream(eligibility: MonetizationEligibility) -> RevenueRoutingDecision:
    cpm_map = {
        RevenueStream.ORGANIC: 0.0,
        RevenueStream.SPONSORED: float(os.getenv("W5_SPONSOR_DEFAULT_CPM_USD", "12")),
        RevenueStream.PREMIUM: float(os.getenv("W5_PREMIUM_CPM_USD", "45")),
        RevenueStream.B2B_API: float(os.getenv("W5_B2B_API_CPM_USD", "8")),
        RevenueStream.SYNDICATION: float(os.getenv("W5_SYNDICATION_CPM_USD", "6")),
        RevenueStream.DATA_LICENSE: float(os.getenv("W5_DATA_LICENSE_CPM_USD", "15")),
    }
    stream = eligibility.primary_stream
    return RevenueRoutingDecision(
        stream=stream,
        estimated_cpm_usd=cpm_map.get(stream, 0.0),
        eligibility=eligibility,
    )
