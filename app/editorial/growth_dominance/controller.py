"""EGDL orchestration — evaluate and enrich content for growth dominance."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.editorial.growth_dominance.arbitration import arbitrate_stability_vs_growth
from app.editorial.growth_dominance.attention_design import enrich_attention_layers, evaluate_attention_design
from app.editorial.growth_dominance.config import egdl_enabled
from app.editorial.growth_dominance.dominance_loops import classify_dominance_loop, loop_to_dict
from app.editorial.growth_dominance.frequency_strategy import resolve_frequency_plan
from app.editorial.growth_dominance.gravity import compute_gravity_score
from app.editorial.growth_dominance.hashtag_engine import apply_growth_hashtags
from app.editorial.growth_dominance.source_graph import evaluate_cluster_source_graph
from app.editorial.growth_dominance.state import record_gravity_event, today_gravity_stats
from app.editorial.stability.anti_pause import evaluate_anti_pause
from app.editorial.stability.growth_decision import evaluate_growth_decision
from app.editorial.stability.packaging import infer_rubric_tag


@dataclass(frozen=True)
class DominanceEvaluation:
    reject: bool
    force_digest: bool
    priority_boost: bool
    body: str
    extras: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "reject": self.reject,
            "force_digest": self.force_digest,
            "priority_boost": self.priority_boost,
            "extras": self.extras,
        }


def evaluate_content_dominance(
    text: str,
    *,
    runtime_dir: str | None,
    editorial_category: str,
    quality_score: float,
    is_breaking: bool,
    publishing_mode: str,
    sources: list[str],
    cluster_size: int = 1,
    newsroom_tz: str = "Europe/Moscow",
) -> DominanceEvaluation:
    if not egdl_enabled():
        return DominanceEvaluation(False, False, False, text, {})

    growth_dec = evaluate_growth_decision(
        text,
        quality_score=quality_score,
        is_breaking=is_breaking,
        publishing_mode=publishing_mode,
        editorial_category=editorial_category,
    )
    post_type = growth_dec.post_type.value

    source_graph = evaluate_cluster_source_graph(
        sources,
        runtime_dir=runtime_dir,
        cluster_size=cluster_size,
    )

    attention = evaluate_attention_design(text, post_type=post_type)
    body = enrich_attention_layers(text, post_type=post_type)
    attention = evaluate_attention_design(body, post_type=post_type)

    gravity = compute_gravity_score(
        body,
        quality_score=quality_score,
        is_breaking=is_breaking,
        post_type=post_type,
        has_hook=attention.has_hook,
        has_meaning=attention.has_meaning,
        has_implication=attention.has_implication,
        source_independence=source_graph.independence_score,
        publishing_mode=publishing_mode,
    )

    if source_graph.downgrade_to_digest and gravity.action not in {"reject_or_synthesis"}:
        gravity = compute_gravity_score(
            body,
            quality_score=max(quality_score, 48.0),
            is_breaking=False,
            post_type="digest",
            has_hook=attention.has_hook,
            has_meaning=attention.has_meaning,
            has_implication=attention.has_implication,
            source_independence=source_graph.independence_score,
            publishing_mode="elastic_fill",
        )

    loop = classify_dominance_loop(
        body,
        post_type=post_type,
        is_breaking=is_breaking,
        publishing_mode=publishing_mode,
        gravity=gravity.total,
    )

    ap = evaluate_anti_pause(newsroom_tz=newsroom_tz)
    arb = arbitrate_stability_vs_growth(
        anti_pause_active=ap.anti_pause_active,
        silence_risk=ap.max_gap_exceeded,
        gravity_action=gravity.action,
        gravity_total=gravity.total,
        growth_reject=growth_dec.reject,
        attention_passes=attention.passes,
        source_downgrade_digest=source_graph.downgrade_to_digest,
        publishing_mode=publishing_mode,
    )

    stats = today_gravity_stats(runtime_dir)
    freq = resolve_frequency_plan(
        high_gravity_events_today=int(stats.get("high_gravity_count") or 0),
        avg_gravity_today=float(stats.get("avg_gravity") or 0),
        posts_today=int(stats.get("posts_published") or 0),
    )

    rubric = infer_rubric_tag(body, editorial_category=editorial_category, post_type=post_type)
    packaged, hashtag_meta = apply_growth_hashtags(
        body,
        editorial_category=editorial_category,
        post_type=post_type if not arb.force_digest else "digest",
        dominance_loop=loop.value,
        secondary_rubric=rubric if rubric.startswith("#") else None,
    )

    record_gravity_event(runtime_dir, gravity_total=gravity.total, loop=loop.value, published=False)

    extras: dict[str, Any] = {
        "editorial_dominance": {
            "dominance_loop": loop_to_dict(loop),
            "gravity": gravity.to_dict(),
            "attention_design": attention.to_dict(),
            "source_graph": source_graph.to_dict(),
            "arbitration": arb.to_dict(),
            "frequency_plan": freq.to_dict(),
            "hashtag_growth": hashtag_meta,
            "growth_decision": growth_dec.to_dict(),
        }
    }

    reject = not arb.publish
    if arb.stability_override:
        reject = False

    return DominanceEvaluation(
        reject=reject,
        force_digest=arb.force_digest,
        priority_boost=arb.priority_boost,
        body=packaged,
        extras=extras,
    )


def enrich_draft_with_dominance(
    draft_body: str,
    *,
    runtime_dir: str | None,
    editorial_category: str,
    quality_score: float,
    is_breaking: bool,
    publishing_mode: str,
    sources: list[str],
    cluster_size: int = 1,
    newsroom_tz: str = "Europe/Moscow",
) -> tuple[str, dict[str, Any]]:
    ev = evaluate_content_dominance(
        draft_body,
        runtime_dir=runtime_dir,
        editorial_category=editorial_category,
        quality_score=quality_score,
        is_breaking=is_breaking,
        publishing_mode=publishing_mode,
        sources=sources,
        cluster_size=cluster_size,
        newsroom_tz=newsroom_tz,
    )
    out_extras: dict[str, Any] = dict(ev.extras)
    if ev.reject:
        out_extras["dominance_reject"] = True
    if ev.priority_boost:
        out_extras["priority_boost"] = True
    if ev.force_digest:
        out_extras["force_digest_slot"] = True
    return ev.body, out_extras
