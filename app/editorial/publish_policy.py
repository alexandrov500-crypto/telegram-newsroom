"""Human-in-the-loop vs auto-publish policy."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any

from app.editorial.desk_filter import DeskDecision
from app.editorial.governance_advanced import evaluate_advanced_governance
from app.editorial.scoring_engine import EditorialScore
from app.editorial.signal_ranking import SignalRankResult, rank_story_signal
from app.editorial.soft_launch import is_soft_launch_mode, soft_launch_thresholds
from app.editorial.source_tiers import aggregate_source_tier
from app.editorial.trust_system import evaluate_editorial_trust


def _auto_signal_threshold() -> float:
    return soft_launch_thresholds().auto_publish_signal_min


@dataclass(frozen=True)
class PublishPolicy:
    auto_publish_eligible: bool
    manual_review_required: bool
    reason: str
    signal_score: float
    source_tier: int
    trust_score: float = 0.0
    soft_launch: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_publish_policy(
    text: str,
    escore: EditorialScore,
    desk: DeskDecision,
    *,
    sources: list[str] | None = None,
    runtime_dir: str | None = None,
    operator_approved: bool = False,
) -> PublishPolicy:
    """
    AUTO-PUBLISH: high signal + tier 1–2 + macro/business/breaking, no controversy flags.
    MANUAL REVIEW: politics, tier-3 weak signal, desk manual hint, unverified framing.
    """
    if not desk.publish:
        return PublishPolicy(
            auto_publish_eligible=False,
            manual_review_required=False,
            reason="desk_rejected",
            signal_score=0.0,
            source_tier=3,
            soft_launch=is_soft_launch_mode(),
        )

    gov = evaluate_advanced_governance(text)
    if gov.auto_block:
        return PublishPolicy(
            auto_publish_eligible=False,
            manual_review_required=False,
            reason=f"governance_block:{gov.reason}",
            signal_score=0.0,
            source_tier=3,
            soft_launch=is_soft_launch_mode(),
        )

    trust = evaluate_editorial_trust(
        text,
        escore,
        sources=sources,
        runtime_dir=runtime_dir,
    )
    sl = soft_launch_thresholds()

    signal: SignalRankResult = rank_story_signal(
        text,
        escore,
        sources=sources,
        runtime_dir=runtime_dir,
        category=desk.editorial_category,
    )
    tier_info = aggregate_source_tier(sources, runtime_dir=runtime_dir)
    manual = (
        desk.manual_review_required
        or signal.manual_review_hint
        or trust.manual_review_required
        or gov.manual_review
        or sl.force_manual_review
    )

    if operator_approved:
        return PublishPolicy(
            auto_publish_eligible=True,
            manual_review_required=False,
            reason="operator_approved",
            signal_score=signal.signal_score,
            source_tier=tier_info.tier,
            trust_score=trust.trust_score,
            soft_launch=sl.force_manual_review,
        )

    if manual or desk.editorial_category in {"reject"}:
        reason = "manual_review_required"
        if trust.manual_review_required:
            reason = f"trust:{','.join(trust.reasons[:2]) or 'low_trust'}"
        elif gov.manual_review:
            reason = f"governance:{gov.reason}"
        return PublishPolicy(
            auto_publish_eligible=False,
            manual_review_required=True,
            reason=reason,
            signal_score=signal.signal_score,
            source_tier=tier_info.tier,
            trust_score=trust.trust_score,
            soft_launch=sl.force_manual_review,
        )

    if trust.trust_score < sl.min_trust_score or signal.signal_score < sl.min_signal_score:
        return PublishPolicy(
            auto_publish_eligible=False,
            manual_review_required=True,
            reason="soft_launch_threshold" if sl.force_manual_review else "trust_or_signal_floor",
            signal_score=signal.signal_score,
            source_tier=tier_info.tier,
            trust_score=trust.trust_score,
            soft_launch=sl.force_manual_review,
        )

    from app.editorial.staging_mode import is_final_staging_mode

    staging_blocks_auto = is_final_staging_mode() and tier_info.tier >= 3

    auto_ok = (
        signal.signal_score >= _auto_signal_threshold()
        and trust.trust_score >= sl.min_trust_score
        and tier_info.tier <= 2
        and not staging_blocks_auto
        and desk.editorial_category in {"macro", "market", "breaking"}
        and desk.priority_tier == "priority"
        and not signal.reject_reason
        and not sl.force_manual_review
    )

    if desk.breaking_override and tier_info.tier <= 2 and signal.signal_score >= 0.55 and trust.trust_score >= 0.5:
        auto_ok = True and not sl.force_manual_review

    if auto_ok:
        return PublishPolicy(
            auto_publish_eligible=True,
            manual_review_required=False,
            reason="auto_publish_high_signal",
            signal_score=signal.signal_score,
            source_tier=tier_info.tier,
            trust_score=trust.trust_score,
            soft_launch=False,
        )

    return PublishPolicy(
        auto_publish_eligible=False,
        manual_review_required=True,
        reason="manual_review_default",
        signal_score=signal.signal_score,
        source_tier=tier_info.tier,
        trust_score=trust.trust_score,
        soft_launch=sl.force_manual_review,
    )
