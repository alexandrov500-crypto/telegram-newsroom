"""MPAES controller — multi-persona adaptive editorial enrichment."""

from __future__ import annotations

from typing import Any

from app.editorial.mpaes.cognitive_segmentation import evaluate_all_segments, primary_segment_for_content
from app.editorial.mpaes.config import dual_audience_min_trust, hub_substitution_min_score, mpaes_enabled
from app.editorial.mpaes.growth_acquisition import apply_discovery_hashtags, build_growth_acquisition_plan
from app.editorial.mpaes.hub_substitution_map import evaluate_hub_substitution
from app.editorial.mpaes.narrative_adapter import adapt_narrative_for_dual_audience
from app.editorial.mpaes.operations_strategy import evaluate_operational_posture
from app.editorial.mpaes.persona_registry import DemographicSegment
from app.editorial.mpaes.source_affinity import evaluate_source_affinity
from app.editorial.mpaes.state import record_mpaes_evaluation


def evaluate_mpaes_state(
    body: str,
    *,
    runtime_dir: str | None,
    editorial_category: str = "",
    sources: list[str] | None = None,
    cluster_size: int = 1,
    is_breaking: bool = False,
    newsroom_tz: str = "Europe/Moscow",
    publishing_mode: str = "core",
    substitution_score: float = 50.0,
    reference_forward_score: float = 0.0,
) -> dict[str, Any]:
    if not mpaes_enabled():
        return {"enabled": False, "dual_audience_trust": 1.0, "hub_fit": True}

    segments = evaluate_all_segments(body, editorial_category=editorial_category)
    hub = evaluate_hub_substitution(body, editorial_category=editorial_category, cluster_size=cluster_size)
    src_aff = evaluate_source_affinity(
        sources or [],
        text=body,
        editorial_category=editorial_category,
        cluster_size=cluster_size,
    )
    posture = evaluate_operational_posture(
        newsroom_tz=newsroom_tz,
        dual_audience_trust=float(segments["dual_audience_trust"]),
        hub_substitution_score=hub.substitution_score,
        publishing_mode=publishing_mode,
    )

    primary = primary_segment_for_content(body, editorial_category)
    growth = build_growth_acquisition_plan(
        body,
        editorial_category=editorial_category,
        primary_segment=primary,
        substitution_score=max(substitution_score, hub.substitution_score),
        is_breaking=is_breaking,
        reference_forward_score=reference_forward_score,
    )

    dual_trust = float(segments["dual_audience_trust"])
    hub_ok = hub.substitution_score >= hub_substitution_min_score()
    dual_ok = dual_trust >= dual_audience_min_trust() or is_breaking or posture.anti_pause_active

    force_digest = False
    if not segments["dual_passes"] and not is_breaking and publishing_mode == "core":
        if not posture.anti_pause_active:
            force_digest = True
    if not hub_ok and not is_breaking and publishing_mode == "core" and not posture.anti_pause_active:
        force_digest = True

    record_mpaes_evaluation(
        runtime_dir,
        dual_audience_trust=dual_trust,
        hub_substitution_score=hub.substitution_score,
        vertical=hub.vertical,
        published=False,
    )

    return {
        "enabled": True,
        "cognitive_segmentation": segments,
        "hub_substitution": hub.to_dict(),
        "source_affinity": src_aff.to_dict(),
        "operational_posture": posture.to_dict(),
        "growth_acquisition": growth.to_dict(),
        "primary_segment": primary.value,
        "dual_audience_trust": dual_trust,
        "hub_fit": hub_ok and dual_ok,
        "force_digest": force_digest,
        "flagship_candidate": src_aff.recommend_flagship and hub.substitution_score >= 70,
        "objective": "intelligent_hub_channel_dual_audience",
    }


def enrich_draft_with_mpaes(
    body: str,
    *,
    runtime_dir: str | None,
    editorial_category: str,
    quality_score: float,
    is_breaking: bool,
    publishing_mode: str,
    sources: list[str],
    cluster_size: int = 1,
    newsroom_tz: str = "Europe/Moscow",
    layer_extras: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    if not mpaes_enabled():
        return body, {}

    layer_extras = layer_extras or {}
    ref_fwd = 0.0
    cse_sub = quality_score
    auh = layer_extras.get("audience_unification")
    if isinstance(auh, dict):
        reader = auh.get("reader_simulation")
        if isinstance(reader, dict):
            ref_fwd = float(reader.get("reader_relevance_score") or 0)

    peos = layer_extras.get("product_os")
    if isinstance(peos, dict):
        cse = peos.get("channel_substitution")
        if isinstance(cse, dict):
            cse_sub = float(cse.get("substitution_score") or cse_sub)
        ref = peos.get("virality_v2")
        if isinstance(ref, dict):
            ref_fwd = max(ref_fwd, float(ref.get("total") or 0))

    evaluation = evaluate_mpaes_state(
        body,
        runtime_dir=runtime_dir,
        editorial_category=editorial_category,
        sources=sources,
        cluster_size=cluster_size,
        is_breaking=is_breaking,
        newsroom_tz=newsroom_tz,
        publishing_mode=publishing_mode,
        substitution_score=cse_sub,
        reference_forward_score=ref_fwd,
    )

    packaged = body
    narrative = adapt_narrative_for_dual_audience(
        packaged,
        editorial_category=editorial_category,
        is_breaking=is_breaking,
    )
    if narrative.applied:
        packaged = narrative.body

    growth_plan = build_growth_acquisition_plan(
        packaged,
        editorial_category=editorial_category,
        primary_segment=DemographicSegment(evaluation["primary_segment"]),
        substitution_score=float(evaluation["hub_substitution"]["substitution_score"]),
        is_breaking=is_breaking,
        reference_forward_score=ref_fwd,
    )
    # Persona-aware discovery tags only when UEOS has not yet applied hashtags.
    if not layer_extras.get("ueos"):
        packaged, tag_meta = apply_discovery_hashtags(packaged, growth_plan)
        evaluation["hashtag_application"] = tag_meta
    else:
        evaluation["hashtag_hints"] = growth_plan.to_dict()

    out: dict[str, Any] = {
        "mpaes": {
            **evaluation,
            "narrative_adaptation": narrative.to_dict(),
        },
    }

    if evaluation.get("force_digest"):
        out["force_digest_slot"] = True
    if evaluation.get("flagship_candidate"):
        out["flagship_post"] = True
    if growth_plan.forward_hook and growth_plan.share_nudge:
        out["growth"] = {
            "forward_hook": growth_plan.forward_hook,
            "acquisition_channel": growth_plan.acquisition_channel,
        }

    return packaged, out


def apply_mpaes_to_decision(
    decision_dict: dict[str, Any],
    mpaes: dict[str, Any],
    *,
    publishing_mode: str = "core",
) -> dict[str, Any]:
    """Adjust OSGCP decision based on dual-audience hub fit (priority 5, before CCD)."""
    inner = mpaes.get("mpaes") if isinstance(mpaes.get("mpaes"), dict) else mpaes
    if not inner or not inner.get("enabled"):
        return decision_dict

    trace = list(decision_dict.get("reasoning_trace") or [])
    force_digest = bool(inner.get("force_digest"))
    dual_trust = float(inner.get("dual_audience_trust") or 0)
    posture = inner.get("operational_posture") if isinstance(inner.get("operational_posture"), dict) else {}

    if posture.get("anti_pause_active") and decision_dict.get("reject"):
        trace.append("mpaes:anti_pause_override")
        decision_dict = {
            **decision_dict,
            "action": "digest",
            "format_mode": "digest",
            "force_digest": True,
            "reject": False,
            "stability_override": True,
            "reasoning_trace": trace,
        }
        return decision_dict

    if force_digest and not decision_dict.get("stability_override"):
        trace.append("mpaes:dual_audience_downgrade")
        decision_dict = {
            **decision_dict,
            "action": "digest",
            "format_mode": "digest",
            "force_digest": True,
            "reject": False,
            "reasoning_trace": trace,
        }
    elif dual_trust < dual_audience_min_trust() and publishing_mode == "core":
        if decision_dict.get("action") == "reject":
            trace.append("mpaes:dual_trust_digest_fallback")
            decision_dict = {
                **decision_dict,
                "action": "digest",
                "format_mode": "digest",
                "force_digest": True,
                "reject": False,
                "reasoning_trace": trace,
            }

    return decision_dict
