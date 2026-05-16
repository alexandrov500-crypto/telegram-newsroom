"""Unified, inspectable editorial decisions for the summarization cluster stage."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Sequence

from db.models import RawPost

from editorial.adaptation import adaptive_threshold_overrides
from editorial.cadence import cadence_should_defer_cluster, topic_dedupe_key
from editorial.diversity import compute_diversity_signals
from editorial.event_models import EventEvolution
from editorial.feedback import feedback_boost_from_stats
from editorial.policy import resolve_effective_policy
from editorial.policy_models import EditorialPolicyBundle
from editorial.relevance import apply_editorial_policy_to_relevance, compute_unified_relevance
from editorial.suppression_memory import duplicate_burst_count, is_suppression_active
from editorial.topic_memory import bump_topic, topic_cooldown_active, topic_saturation
from editorial.trends import source_convergence_score


class EditorialPipelineOutcome(str, Enum):
    PROCEED_CLUSTER = "proceed_cluster"
    SUPPRESS = "suppress"
    DEFER_TICK = "defer"
    COOLDOWN = "cooldown"
    ESCALATE_PRIORITY = "escalate_priority"
    HOLD_FOR_REVIEW = "hold_for_review"


def _cluster_urgency(evo: EventEvolution, rel_total: float, posts: list[RawPost]) -> bool:
    if evo.kind == "new" and rel_total >= 58.0:
        return True
    if source_convergence_score(posts) >= 0.55 and rel_total >= 48.0:
        return True
    if evo.kind == "new" and float(evo.continuity_score) < 0.35 and rel_total >= 52.0:
        return True
    return False


@dataclass(slots=True)
class UnifiedEditorialDecision:
    outcome: EditorialPipelineOutcome
    suppress_generation: bool
    defer_to_next_tick: bool
    hold_for_review: bool
    escalate_priority: bool
    reasons: tuple[str, ...]
    relevance: Any
    score_breakdown: dict[str, Any]
    contributing: tuple[str, ...]
    policy_refs: tuple[str, ...]
    adaptation: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "suppress_generation": self.suppress_generation,
            "defer_to_next_tick": self.defer_to_next_tick,
            "hold_for_review": self.hold_for_review,
            "escalate_priority": self.escalate_priority,
            "reasons": list(self.reasons),
            "relevance": self.relevance.to_dict() if hasattr(self.relevance, "to_dict") else {},
            "score_breakdown": dict(self.score_breakdown),
            "contributing_heuristics": list(self.contributing),
            "policy_refs": list(self.policy_refs),
            "adaptation": dict(self.adaptation),
        }


def evaluate_unified_cluster_stage(
    posts: list[RawPost],
    *,
    settings: Any,
    evolution: EventEvolution,
    topic_hint: str,
    fingerprint: str,
    combined_text: str,
    channel_scores: dict[str, dict[str, Any]],
    feedback_stats: dict[str, Any] | None,
    duplicate_similarity_pct: float | None,
    entity_hits: int,
    entity_norms: Sequence[str],
    policy_bundle: EditorialPolicyBundle,
    dominant_channel_key: str,
) -> UnifiedEditorialDecision:
    runtime_dir = str(getattr(settings, "runtime_state_dir", "") or "")
    policy, pref_trace = resolve_effective_policy(policy_bundle, dominant_channel_key)
    row = bump_topic(runtime_dir, topic_hint=topic_hint, fingerprint=fingerprint)
    burst_th = max(3, min(20, int(round(8.0 / max(0.45, float(policy.oversaturation_multiplier))))))
    sat, sat_reason = topic_saturation(row, burst_threshold=burst_th)
    cooldown = topic_cooldown_active(row)
    boost = feedback_boost_from_stats(feedback_stats)
    rel = compute_unified_relevance(
        posts,
        channel_scores=channel_scores,
        evolution=evolution,
        topic_row=row,
        entity_hits=entity_hits,
        duplicate_similarity_pct=duplicate_similarity_pct,
        feedback_boost=boost,
    )
    diversity = compute_diversity_signals(posts, topic_hint, list(entity_norms))
    apply_editorial_policy_to_relevance(
        rel,
        policy,
        topic_hint=topic_hint,
        combined_text=combined_text,
        diversity=diversity,
        topic_row=row,
        evolution=evolution,
    )
    adap = adaptive_threshold_overrides(feedback_stats, policy)
    adap_notes = tuple(str(x) for x in (adap.get("notes") or ()))
    thr_sup = float(adap["relevance_suppress_below"])
    thr_cd = float(adap["relevance_cooldown_update_below"])
    thr_dup = float(adap["duplicate_signal_suppress_above"])

    reasons: list[str] = []
    contributing: list[str] = []
    policy_refs = tuple(pref_trace)

    if is_suppression_active(runtime_dir, fingerprint):
        reasons.append("suppression_ttl_active")
        contributing.append("suppression_memory")
        return UnifiedEditorialDecision(
            outcome=EditorialPipelineOutcome.SUPPRESS,
            suppress_generation=True,
            defer_to_next_tick=False,
            hold_for_review=False,
            escalate_priority=False,
            reasons=tuple(reasons),
            relevance=rel,
            score_breakdown={"relevance_total": rel.total, "diversity": asdict(diversity)},
            contributing=tuple(contributing),
            policy_refs=policy_refs,
            adaptation=adap,
        )

    if duplicate_burst_count(runtime_dir) >= 10:
        reasons.append("duplicate_storm_suppress")
        contributing.append("suppression_memory.duplicate_burst")
        return UnifiedEditorialDecision(
            outcome=EditorialPipelineOutcome.SUPPRESS,
            suppress_generation=True,
            defer_to_next_tick=False,
            hold_for_review=False,
            escalate_priority=False,
            reasons=tuple(reasons),
            relevance=rel,
            score_breakdown={"relevance_total": rel.total, "duplicate_burst": duplicate_burst_count(runtime_dir)},
            contributing=tuple(contributing),
            policy_refs=policy_refs,
            adaptation=adap,
        )

    urgency = _cluster_urgency(evolution, rel.total, posts)
    defer, dreasons = cadence_should_defer_cluster(
        settings,
        runtime_dir,
        policy,
        topic_key=topic_dedupe_key(topic_hint),
        urgency=urgency,
    )
    if defer:
        reasons.extend(dreasons)
        contributing.append("cadence")
        return UnifiedEditorialDecision(
            outcome=EditorialPipelineOutcome.DEFER_TICK,
            suppress_generation=True,
            defer_to_next_tick=True,
            hold_for_review=False,
            escalate_priority=False,
            reasons=tuple(reasons),
            relevance=rel,
            score_breakdown={"relevance_total": rel.total, "cadence": dreasons},
            contributing=tuple(contributing),
            policy_refs=policy_refs,
            adaptation=adap,
        )

    suppress = False
    if sat and rel.duplicate_suppression > thr_dup:
        suppress = True
        reasons.append("saturated_topic_and_high_duplicate_signal")
        contributing.extend(["topic_memory.saturation", "relevance.duplicate_suppression"])
    if cooldown and evolution.kind == "update" and rel.total < thr_cd:
        suppress = True
        reasons.append("cooldown_update_low_relevance")
        contributing.extend(["topic_memory.cooldown", "event_evolution.update"])
    if rel.total < thr_sup and evolution.kind != "new":
        suppress = True
        reasons.append("very_low_relevance_non_new")
        contributing.append("relevance.total")

    escalate = bool(urgency and sat and rel.total < thr_cd + 8) and not suppress
    hold = (not suppress) and (thr_cd - 6) <= rel.total < thr_cd and rel.duplicate_suppression > 0.62
    if hold:
        reasons.append("policy_hold_for_review_duplicate_signal")
        contributing.append("relevance.duplicate_suppression")

    if suppress:
        outcome = EditorialPipelineOutcome.COOLDOWN if cooldown else EditorialPipelineOutcome.SUPPRESS
    elif hold:
        outcome = EditorialPipelineOutcome.HOLD_FOR_REVIEW
    elif escalate:
        outcome = EditorialPipelineOutcome.ESCALATE_PRIORITY
        contributing.append("urgency_with_saturation")
    else:
        outcome = EditorialPipelineOutcome.PROCEED_CLUSTER

    score_breakdown = {
        "relevance_total": rel.total,
        "thresholds": {"suppress_below": thr_sup, "cooldown_update_below": thr_cd, "dup_signal_above": thr_dup},
        "diversity": {
            "unique_channels": diversity.unique_channels,
            "unique_channel_ratio": diversity.unique_channel_ratio,
            "entity_repetition": diversity.entity_token_repetition,
        },
        "topic_saturation": sat,
        "topic_cooldown": cooldown,
        "adaptation_notes": list(adap_notes),
    }

    return UnifiedEditorialDecision(
        outcome=outcome,
        suppress_generation=suppress or False,
        defer_to_next_tick=False,
        hold_for_review=hold and not suppress,
        escalate_priority=escalate and not suppress,
        reasons=tuple(reasons),
        relevance=rel,
        score_breakdown=score_breakdown,
        contributing=tuple(contributing) if contributing else ("baseline",),
        policy_refs=policy_refs,
        adaptation=adap,
    )
