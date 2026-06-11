"""UEOS Controller — meta-orchestrator above Stability, EGDL, AUH."""

from __future__ import annotations

from typing import Any

from app.editorial.stability.anti_pause import evaluate_anti_pause
from app.editorial.unified_operating_system.arbitration import arbitrate_layer_conflicts
from app.editorial.unified_operating_system.audience_replacement import evaluate_channel_replacement
from app.editorial.unified_operating_system.config import (
    ueos_digest_threshold,
    ueos_enabled,
    ueos_publish_threshold,
)
from app.editorial.unified_operating_system.content_principle import enrich_content_principle, evaluate_content_principle
from app.editorial.unified_operating_system.cross_source_intelligence_merger import merge_world_signal
from app.editorial.unified_operating_system.daily_autopilot import AutopilotMode, resolve_autopilot_mode
from app.editorial.unified_operating_system.hashtag_strategy_v2 import apply_hashtag_strategy_v2
from app.editorial.unified_operating_system.state import record_ueos_decision
from app.editorial.unified_operating_system.ueos_score import UEOSAction, compute_ueos_score
from app.editorial.unified_operating_system.user_reality_model import evaluate_user_reality


def _layer_metrics(layer_extras: dict[str, Any]) -> dict[str, Any]:
    dom = layer_extras.get("editorial_dominance") if isinstance(layer_extras.get("editorial_dominance"), dict) else {}
    auh = layer_extras.get("audience_unification") if isinstance(layer_extras.get("audience_unification"), dict) else {}
    grav = dom.get("gravity") if isinstance(dom.get("gravity"), dict) else {}
    att = dom.get("attention_design") if isinstance(dom.get("attention_design"), dict) else {}
    crs = auh.get("crs") if isinstance(auh.get("crs"), dict) else {}
    ues = auh.get("ues") if isinstance(auh.get("ues"), dict) else {}
    reader = auh.get("reader_simulation") if isinstance(auh.get("reader_simulation"), dict) else {}
    return {
        "gravity_total": float(grav.get("total") or 50.0),
        "attention_design": att,
        "crs_total": float(crs.get("total") or 50.0),
        "ues_total": float(ues.get("total") or 50.0),
        "reader_unification": float(reader.get("reader_unification_score") or 50.0),
        "cross_breadth": int(reader.get("cross_interest_breadth") or 0),
    }


def enrich_draft_with_ueos(
    body: str,
    *,
    runtime_dir: str | None,
    editorial_category: str,
    quality_score: float,
    is_breaking: bool,
    publishing_mode: str,
    cluster_size: int = 1,
    cluster_texts: list[str] | None = None,
    newsroom_tz: str = "Europe/Moscow",
    layer_extras: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    if not ueos_enabled():
        return body, {}

    layer_extras = layer_extras or {}
    metrics = _layer_metrics(layer_extras)
    ap = evaluate_anti_pause(newsroom_tz=newsroom_tz)

    dominance_reject = bool(layer_extras.get("dominance_reject"))
    auh_reject = bool(layer_extras.get("auh_reject"))

    packaged = body
    csim_meta: dict[str, Any] = {"applied": False}
    cross_intel = 40.0

    autopilot_pre = resolve_autopilot_mode(
        is_breaking=is_breaking,
        gravity_total=metrics["gravity_total"],
        anti_pause_active=ap.anti_pause_active,
        publishing_mode=publishing_mode,
        cluster_size=cluster_size,
        quality_score=quality_score,
        compression_required=False,
    )

    texts = cluster_texts or ([body] if body else [])
    if autopilot_pre.use_csim and len(texts) >= 2:
        merged, csim = merge_world_signal(texts, topic_hint=editorial_category)
        if merged:
            packaged = merged
            cross_intel = csim.intelligence_score
            csim_meta = {"applied": True, **csim.to_dict()}

    principle = evaluate_content_principle(packaged)
    principle_meta: dict[str, Any] = {"principle": principle.to_dict()}
    if principle.needs_rewrite:
        packaged, principle_meta = enrich_content_principle(packaged)
        principle = evaluate_content_principle(packaged)

    urm = evaluate_user_reality(packaged)
    reader_unification = max(metrics["reader_unification"], urm.reader_unification_score)

    replacement = evaluate_channel_replacement(
        packaged,
        cross_topic_breadth=max(metrics["cross_breadth"], len(urm.matched_topics)),
        cluster_size=cluster_size,
        crs_total=metrics["crs_total"],
    )

    layer_arb = arbitrate_layer_conflicts(
        anti_pause_active=ap.anti_pause_active,
        publishing_mode=publishing_mode,
        gravity_total=metrics["gravity_total"],
        crs_total=metrics["crs_total"],
        ues_total=metrics["ues_total"],
        dominance_reject=dominance_reject,
        auh_reject=auh_reject,
        cluster_size=cluster_size,
        quality_score=quality_score,
        replaces_channels=replacement.replaces_external_channels,
    )

    autopilot = resolve_autopilot_mode(
        is_breaking=is_breaking,
        gravity_total=metrics["gravity_total"],
        anti_pause_active=ap.anti_pause_active,
        publishing_mode=publishing_mode,
        cluster_size=cluster_size,
        quality_score=quality_score,
        compression_required=layer_arb.compression_required,
    )

    if csim_meta.get("applied"):
        cross_intel = float(csim_meta.get("intelligence_score") or cross_intel)

    ueos = compute_ueos_score(
        ues_total=metrics["ues_total"],
        crs_total=metrics["crs_total"],
        gravity_total=metrics["gravity_total"],
        reader_unification=reader_unification,
        cross_source_intelligence=cross_intel,
        attention_design=metrics["attention_design"],
        compress_mode=autopilot.mode == AutopilotMode.COMPRESSION and csim_meta.get("applied", False),
        publishing_mode=publishing_mode,
    )

    reject = ueos.action == UEOSAction.REJECT
    force_digest = ueos.action in {
        UEOSAction.PUBLISH_DIGEST,
        UEOSAction.COMPRESS_AND_PUBLISH,
        UEOSAction.STABILITY_FALLBACK,
    }
    priority = ueos.action == UEOSAction.PUBLISH_FLAGSHIP or autopilot.immediate_publish
    flagship = ueos.action == UEOSAction.PUBLISH_FLAGSHIP

    publish_thr = float(ueos_publish_threshold())
    digest_thr = float(ueos_digest_threshold())

    if not replacement.replaces_external_channels and not layer_arb.stability_override:
        if ueos.total < publish_thr:
            reject = publishing_mode == "core"
            force_digest = True
        if ueos.total < digest_thr and publishing_mode == "core":
            reject = True

    if layer_arb.stability_override and reject:
        reject = False
        force_digest = True

    if not principle.complete and reject and publishing_mode == "core" and not layer_arb.stability_override:
        reject = True

    if ueos.action == UEOSAction.DELAY:
        reject = publishing_mode == "core"

    packaged, hashtag_meta = apply_hashtag_strategy_v2(
        packaged,
        editorial_category=editorial_category,
        flagship=flagship,
    )

    mpaes = layer_extras.get("mpaes") if isinstance(layer_extras.get("mpaes"), dict) else {}
    mpaes_tags = mpaes.get("growth_acquisition") if isinstance(mpaes.get("growth_acquisition"), dict) else {}
    discovery = mpaes_tags.get("discovery_hashtags") or []
    if discovery:
        import re

        try:
            from app.editorial.clean_channel_copy import clean_channel_copy_enabled

            skip_tags = clean_channel_copy_enabled()
        except Exception:
            skip_tags = False
        if not skip_tags:
            existing = set(re.findall(r"#\w+", packaged or ""))
            extra = [t for t in discovery if t not in existing]
            if extra and len(existing) < 2:
                packaged = f"{(packaged or '').strip()} {' '.join(extra[:1])}".strip()
                hashtag_meta = {**hashtag_meta, "mpaes_discovery_merged": extra[:1]}

    record_ueos_decision(
        runtime_dir,
        ueos_total=ueos.total,
        action=ueos.action.value,
        conflicts=list(layer_arb.conflicts_resolved),
        compression=bool(csim_meta.get("applied")),
        replacement_score=replacement.estimated_channels_replaced,
        published=False,
    )

    out_extras: dict[str, Any] = {
        "ueos": {
            "score": ueos.to_dict(),
            "autopilot": autopilot.to_dict(),
            "layer_arbitration": layer_arb.to_dict(),
            "user_reality_model": urm.to_dict(),
            "channel_replacement": replacement.to_dict(),
            "content_principle": principle_meta,
            "csim": csim_meta,
            "hashtag_v2": hashtag_meta,
            "decision": ueos.action.value,
            "objective": "maximize_cognitive_replacement_of_external_information_ecosystem",
        }
    }

    if reject:
        out_extras["ueos_reject"] = True
        out_extras["stability_reject"] = True
    else:
        out_extras.pop("stability_reject", None)
        out_extras.pop("ueos_reject", None)
        out_extras.pop("dominance_reject", None)
        out_extras.pop("auh_reject", None)

    if force_digest:
        out_extras["force_digest_slot"] = True
    if priority or ueos.skip_cadence_cap:
        out_extras["priority_boost"] = True
    if flagship:
        out_extras["flagship_post"] = True

    return packaged, out_extras
