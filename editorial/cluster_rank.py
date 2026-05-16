"""Pipeline cluster decision: suppression + explainable ranking metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from db.models import RawPost

from editorial.event_models import EventEvolution
from editorial.pipeline_decision import evaluate_unified_cluster_stage
from editorial.policy import dominant_channel_key, load_editorial_policy_bundle
from editorial.relevance import RelevanceBreakdown


@dataclass(slots=True)
class ClusterPipelineDecision:
    suppress: bool
    defer_to_next_tick: bool
    hold_for_review: bool
    escalate_priority: bool
    suppression_reasons: tuple[str, ...]
    relevance: RelevanceBreakdown
    ranking_notes: tuple[str, ...] = field(default_factory=tuple)
    unified: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "suppress": self.suppress,
            "defer_to_next_tick": self.defer_to_next_tick,
            "hold_for_review": self.hold_for_review,
            "escalate_priority": self.escalate_priority,
            "suppression_reasons": list(self.suppression_reasons),
            "relevance": self.relevance.to_dict(),
            "ranking_notes": list(self.ranking_notes),
            "editorial_pipeline": dict(self.unified),
        }


def evaluate_cluster_for_pipeline(
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
    entity_norms: Sequence[str] | None = None,
) -> ClusterPipelineDecision:
    bundle = load_editorial_policy_bundle(settings)
    dom = dominant_channel_key(posts)
    uni = evaluate_unified_cluster_stage(
        posts,
        settings=settings,
        evolution=evolution,
        topic_hint=topic_hint,
        fingerprint=fingerprint,
        combined_text=combined_text,
        channel_scores=channel_scores,
        feedback_stats=feedback_stats,
        duplicate_similarity_pct=duplicate_similarity_pct,
        entity_hits=entity_hits,
        entity_norms=tuple(entity_norms or ()),
        policy_bundle=bundle,
        dominant_channel_key=dom,
    )
    notes: list[str] = list(uni.relevance.policy_notes or ())
    notes.extend(str(x) for x in (uni.adaptation.get("notes") or ()) if x)
    sup_reasons = tuple(uni.reasons) if (uni.suppress_generation or uni.defer_to_next_tick) else ()
    return ClusterPipelineDecision(
        suppress=bool(uni.suppress_generation and not uni.defer_to_next_tick),
        defer_to_next_tick=bool(uni.defer_to_next_tick),
        hold_for_review=bool(uni.hold_for_review),
        escalate_priority=bool(uni.escalate_priority),
        suppression_reasons=sup_reasons,
        relevance=uni.relevance,
        ranking_notes=tuple(notes),
        unified=uni.to_dict(),
    )
