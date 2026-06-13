"""Channel Product controller — growth loop + viral packaging after UEOS."""

from __future__ import annotations

from typing import Any

from app.editorial.channel_product.acquisition_attribution import build_acquisition_attribution
from app.editorial.channel_product.config import (
    channel_product_enabled,
    growth_brief_auto_threshold,
    open_loop_default_enabled,
    share_nudge_default_enabled,
)
from app.editorial.channel_product.cta_optimizer import select_cta_variant
from app.editorial.channel_product.feedback_bridge import global_momentum, topic_weights_from_feedback
from app.editorial.channel_product.growth_loop import classify_growth_loop
from app.editorial.channel_product.state import record_channel_product_event
from app.editorial.channel_product.viral_mechanics import evaluate_viral_mechanics
from app.growth_layer.format.profiles import publish_format_mode


def _extract_ueos(layer_extras: dict[str, Any]) -> dict[str, Any]:
    ueos = layer_extras.get("ueos") if isinstance(layer_extras.get("ueos"), dict) else {}
    score = ueos.get("score") if isinstance(ueos.get("score"), dict) else {}
    return {
        "total": float(score.get("total") or 50.0),
        "decision": str(ueos.get("decision") or "publish"),
        "flagship": bool(layer_extras.get("flagship_post")),
    }


def _extract_crs(layer_extras: dict[str, Any]) -> float:
    auh = layer_extras.get("audience_unification") if isinstance(layer_extras.get("audience_unification"), dict) else {}
    crs = auh.get("crs") if isinstance(auh.get("crs"), dict) else {}
    return float(crs.get("total") or 50.0)


def enrich_draft_with_channel_product(
    body: str,
    *,
    runtime_dir: str | None,
    editorial_category: str,
    publishing_mode: str,
    is_breaking: bool = False,
    layer_extras: dict[str, Any] | None = None,
    forwardability: float = 0.0,
) -> tuple[str, dict[str, Any]]:
    if not channel_product_enabled():
        return body, {}

    layer_extras = layer_extras or {}
    ueos = _extract_ueos(layer_extras)
    crs = _extract_crs(layer_extras)
    is_digest = bool(layer_extras.get("force_digest_slot")) or publishing_mode != "core"
    anti_pause = publishing_mode in {"elastic_fill", "editorial_synthesis"}

    viral = evaluate_viral_mechanics(
        body,
        ueos_total=ueos["total"],
        crs_total=crs,
        flagship=ueos["flagship"],
        growth_brief_min=growth_brief_auto_threshold(),
    )

    loop = classify_growth_loop(
        ueos_total=ueos["total"],
        flagship=ueos["flagship"],
        virality_score=viral.reference_forward_score,
        forwardability=forwardability,
        is_digest=is_digest,
        anti_pause=anti_pause,
    )

    topic_w = topic_weights_from_feedback(runtime_dir)
    cta = select_cta_variant(body, topic_weights=topic_w)

    fmt = "subscriber_wire" if publish_format_mode() == "subscriber_wire" else (
        "growth_brief" if viral.use_growth_brief else "cb_brief"
    )
    attr = build_acquisition_attribution(
        draft_body=body,
        loop_stage=loop.stage.value,
        cta_variant_id=cta.variant_id,
        format_profile=fmt,
    )

    momentum = global_momentum(runtime_dir)
    enable_share = viral.enable_share_nudge and share_nudge_default_enabled()
    enable_open = viral.enable_open_loop and open_loop_default_enabled()

    record_channel_product_event(
        runtime_dir,
        loop_stage=loop.stage.value,
        viral_tier=viral.viral_tier,
        cta_variant_id=cta.variant_id,
        reference_forward_score=viral.reference_forward_score,
        published=False,
    )

    cp_extras: dict[str, Any] = {
        "channel_product": {
            "growth_loop": loop.to_dict(),
            "viral_mechanics": viral.to_dict(),
            "cta_variant": cta.to_dict(),
            "acquisition": attr.to_dict(),
            "format_profile": fmt,
            "viral_tier": viral.viral_tier,
            "reference_forward_score": viral.reference_forward_score,
            "share_nudge": cta.share_nudge if enable_share else "",
            "subscribe_line": cta.subscribe_line,
            "enable_open_loop": enable_open,
            "enable_share_nudge": enable_share,
            "feedback_momentum": momentum,
            "editorial_category": editorial_category,
            "objective": "single_channel_substitution_rate",
        },
        "growth": {
            "format_profile": fmt,
            "virality_score": int(viral.reference_forward_score),
            "virality_tier": viral.viral_tier,
            "channel_product_loop": loop.stage.value,
            "experiment_id": attr.experiment_id,
        },
    }

    return body, cp_extras
