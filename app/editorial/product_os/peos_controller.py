"""PEOS controller — final product decision: will this replace other channels?"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.editorial.channel_product.acquisition_attribution import build_acquisition_attribution
from app.editorial.channel_product.feedback_bridge import topic_weights_from_feedback
from app.editorial.product_os.audience_reality_v2 import evaluate_audience_reality_v2
from app.editorial.product_os.channel_substitution_engine import evaluate_channel_substitution
from app.editorial.product_os.config import product_os_enabled
from app.editorial.product_os.content_format import classify_content_format
from app.editorial.product_os.contextual_cta import select_contextual_cta
from app.editorial.product_os.daily_operating_model import evaluate_daily_slot
from app.editorial.product_os.product_gravity import PGAction, compute_product_gravity
from app.editorial.product_os.replacement_loop import classify_replacement_stage
from app.editorial.product_os.source_strategy import evaluate_source_strategy
from app.editorial.product_os.state import record_peos_evaluation
from app.editorial.product_os.telegram_mechanics import build_telegram_mechanics
from app.editorial.product_os.virality_v2 import compute_reference_forward_score
from app.editorial.unified_operating_system.content_principle import evaluate_content_principle


def enrich_draft_with_product_os(
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
    if not product_os_enabled():
        return body, {}

    layer_extras = layer_extras or {}
    force_digest = bool(layer_extras.get("force_digest_slot"))
    is_flagship = bool(layer_extras.get("flagship_post"))

    principle = evaluate_content_principle(body)
    cross_breadth = 0
    auh = layer_extras.get("audience_unification")
    if isinstance(auh, dict):
        reader = auh.get("reader_simulation")
        if isinstance(reader, dict):
            cross_breadth = int(reader.get("cross_interest_breadth") or 0)

    cse = evaluate_channel_substitution(body, cluster_size=cluster_size, cross_topic_breadth=cross_breadth)
    arm = evaluate_audience_reality_v2(body, feedback_topic_weights=topic_weights_from_feedback(runtime_dir))

    ref = compute_reference_forward_score(
        body,
        cluster_size=cluster_size,
        cross_domain_density=cse.cross_domain_density,
        has_why_it_matters=principle.has_why,
    )

    pg = compute_product_gravity(
        quality_score=quality_score,
        cross_domain_density=cse.cross_domain_density,
        substitution_score=float(cse.to_dict()["substitution_score"]),
        clarity=ref.clarity,
        reference_forward_total=ref.total,
        novelty_hint=ref.surprise / 100.0,
        publishing_mode=publishing_mode,
    )

    src = evaluate_source_strategy(sources, cluster_size=cluster_size)
    fmt = classify_content_format(
        body,
        is_breaking=is_breaking,
        force_digest=force_digest,
        post_type=str(
            (layer_extras.get("editorial_stability") or {}).get("growth_decision", {}).get("post_type", "")
            if isinstance(layer_extras.get("editorial_stability"), dict)
            else ""
        ),
    )

    daily = evaluate_daily_slot(fmt, runtime_dir=runtime_dir, pg_total=pg.total, low_signal_day=pg.total < 55)
    replacement = classify_replacement_stage(
        pg_total=pg.total,
        reference_forward_score=ref.total,
        substitution_score=float(cse.to_dict()["substitution_score"]),
        is_digest=force_digest or fmt.value == "digest",
        is_flagship=is_flagship or pg.action == PGAction.FLAGSHIP,
        publishing_mode=publishing_mode,
    )

    cta = select_contextual_cta(
        content_format=fmt,
        is_breaking=is_breaking,
        reference_forward_score=ref.total,
        trigger_forward=ref.trigger_forward,
    )

    try:
        tz = ZoneInfo(newsroom_tz)
        hour_local = datetime.now(tz).hour
    except Exception:
        hour_local = 12

    tg = build_telegram_mechanics(
        content_format=fmt,
        replacement_stage=replacement.stage,
        pg_total=pg.total,
        trigger_forward=ref.trigger_forward,
        hour_local=hour_local,
    )

    attr = build_acquisition_attribution(
        draft_body=body,
        loop_stage=replacement.stage.value,
        cta_variant_id=cta.cta_type.value,
        format_profile="growth_brief" if fmt.value in {"model", "insight", "digest"} else "cb_brief",
    )

    record_peos_evaluation(
        runtime_dir,
        pg_total=pg.total,
        substitution_score=float(cse.to_dict()["substitution_score"]),
        forward_prediction=ref.forward_prediction,
        cta_type=cta.cta_type.value,
        content_format=fmt.value,
        published=False,
    )

    reject = pg.action == PGAction.REJECT and publishing_mode == "core"
    if not cse.valid and pg.total < 65 and publishing_mode == "core":
        reject = True
    if src.single_class_only and pg.action == PGAction.FLAGSHIP:
        force_digest = True
    if src.force_compress and not cse.valid:
        force_digest = True
    if not daily.within_daily_budget and pg.total < 78:
        force_digest = True
    if not principle.complete and pg.total < 70 and publishing_mode == "core":
        force_digest = True

    if publishing_mode in {"elastic_fill", "editorial_synthesis"} and reject:
        reject = False
        force_digest = True

    out_extras: dict[str, Any] = {
        "product_os": {
            "product_gravity": pg.to_dict(),
            "channel_substitution": cse.to_dict(),
            "virality_v2": ref.to_dict(),
            "audience_reality_v2": arm.to_dict(),
            "content_format": fmt.value,
            "source_strategy": src.to_dict(),
            "daily_slot": daily.to_dict(),
            "replacement_loop": replacement.to_dict(),
            "contextual_cta": cta.to_dict(),
            "telegram_mechanics": tg.to_dict(),
            "content_principle": principle.to_dict(),
            "acquisition": attr.to_dict(),
            "objective": "maximize_cognitive_substitution_per_user_per_day",
            "question": "will_this_replace_other_channels_in_user_mind",
        },
        "channel_product": {
            "share_nudge": cta.line if cta.enable_share else "",
            "subscribe_line": "",
            "enable_share_nudge": cta.enable_share,
            "enable_open_loop": replacement.stage.value in {"return", "habit"},
            "format_profile": "growth_brief" if fmt.value in {"model", "insight", "digest"} else "cb_brief",
            "reference_forward_score": ref.total,
            "viral_tier": "reference_forward" if ref.trigger_forward else "standard",
            "product_os_loop": replacement.stage.value,
        },
        "growth": {
            "format_profile": "growth_brief" if fmt.value in {"model", "insight", "digest"} else "cb_brief",
            "virality_score": int(ref.total),
            "virality_tier": "reference_forward" if ref.trigger_forward else "standard",
            "experiment_id": attr.experiment_id,
            "product_os_format": fmt.value,
        },
    }

    if reject:
        out_extras["product_os_reject"] = True
        out_extras["stability_reject"] = True
    if force_digest:
        out_extras["force_digest_slot"] = True
    if pg.action == PGAction.FLAGSHIP or is_flagship:
        out_extras["flagship_post"] = True
        out_extras["priority_boost"] = True
    elif pg.skip_cadence_cap:
        out_extras["priority_boost"] = True

    return body, out_extras
