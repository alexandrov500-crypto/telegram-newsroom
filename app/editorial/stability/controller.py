"""Orchestration helpers for stability layer integration."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.editorial.stability.growth_decision import evaluate_growth_decision
from app.editorial.stability.mode_controller import StabilityContext, resolve_publishing_mode
from app.editorial.stability.packaging import apply_editorial_packaging
from app.editorial.stability.slo import record_stability_publish


def evaluate_stability_context(
    *,
    newsroom_tz: str = "Europe/Moscow",
    cluster_size: int = 0,
    governance_blocked: bool = False,
    desk_blocked: bool = False,
    no_raw_posts: bool = False,
) -> StabilityContext:
    return resolve_publishing_mode(
        newsroom_tz=newsroom_tz,
        cluster_size=cluster_size,
        governance_blocked=governance_blocked,
        desk_blocked=desk_blocked,
        no_raw_posts=no_raw_posts,
    )


def _wire_beat_advisory_only(dom_extras: dict[str, Any], *, publishing_mode: str, quality_score: float) -> dict[str, Any]:
    """News beat wire: layer rejects are advisory — publish gates decide."""
    try:
        from app.editorial.ai_editorial_reviewer import autonomous_editorial_mode_enabled
        from app.editorial.news_channel_beat import news_channel_beat_enabled

        if (
            publishing_mode == "core"
            and news_channel_beat_enabled()
            and autonomous_editorial_mode_enabled()
            and quality_score >= 40
        ):
            for key in (
                "stability_reject",
                "ueos_reject",
                "product_os_reject",
                "dominance_reject",
                "auh_reject",
            ):
                dom_extras.pop(key, None)
    except Exception:
        pass
    return dom_extras


def enrich_draft_for_stability(
    draft_body: str,
    *,
    runtime_dir: str | None,
    editorial_category: str,
    quality_score: float,
    is_breaking: bool,
    publishing_mode: str,
    sources: list[str],
    cluster_size: int = 1,
    cluster_texts: list[str] | None = None,
    newsroom_tz: str = "Europe/Moscow",
) -> tuple[str, dict[str, Any]]:
    dom_extras_seed: dict[str, Any] = {"sources": list(sources or [])}

    decision = evaluate_growth_decision(
        draft_body,
        quality_score=quality_score,
        is_breaking=is_breaking,
        publishing_mode=publishing_mode,
        editorial_category=editorial_category,
    )
    if decision.reject and publishing_mode == "core":
        try:
            from app.editorial.ai_editorial_reviewer import autonomous_editorial_mode_enabled
            from app.editorial.growth_dominance.config import egdl_enabled
            from app.editorial.news_channel_beat import news_channel_beat_enabled

            if news_channel_beat_enabled() and autonomous_editorial_mode_enabled():
                pass  # wire beat — growth reject is non-terminal; UEOS/publish gates decide
            elif not egdl_enabled():
                return draft_body, {"growth_decision": decision.to_dict(), "stability_reject": True}
        except Exception:
            return draft_body, {"growth_decision": decision.to_dict(), "stability_reject": True}

    packaged = draft_body
    pkg_meta: dict[str, Any] = {}
    dom_extras: dict[str, Any] = dict(dom_extras_seed)
    try:
        from app.editorial.growth_dominance.config import egdl_enabled

        if egdl_enabled():
            from app.editorial.growth_dominance.controller import enrich_draft_with_dominance

            packaged, dom_extras = enrich_draft_with_dominance(
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
            if dom_extras.get("dominance_reject") and publishing_mode == "core":
                pass  # UEOS is final arbiter
    except Exception:
        pass

    try:
        from app.editorial.audience_unification.config import auh_enabled

        if auh_enabled():
            from app.editorial.audience_unification.controller import enrich_draft_with_auh

            packaged, auh_extras = enrich_draft_with_auh(
                packaged,
                runtime_dir=runtime_dir,
                editorial_category=editorial_category,
                quality_score=quality_score,
                publishing_mode=publishing_mode,
                cluster_size=cluster_size,
                newsroom_tz=newsroom_tz,
                dom_extras=dom_extras or None,
            )
            dom_extras = {**dom_extras, **auh_extras}
    except Exception:
        pass

    try:
        from app.editorial.mpaes.config import mpaes_enabled

        if mpaes_enabled():
            from app.editorial.mpaes.controller import enrich_draft_with_mpaes

            packaged, mpaes_extras = enrich_draft_with_mpaes(
                packaged,
                runtime_dir=runtime_dir,
                editorial_category=editorial_category,
                quality_score=quality_score,
                is_breaking=is_breaking,
                publishing_mode=publishing_mode,
                sources=sources,
                cluster_size=cluster_size,
                newsroom_tz=newsroom_tz,
                layer_extras=dom_extras or None,
            )
            dom_extras = {**dom_extras, **mpaes_extras}
    except Exception:
        pass

    try:
        from app.editorial.unified_operating_system.config import ueos_enabled

        if ueos_enabled():
            from app.editorial.unified_operating_system.ueos_controller import enrich_draft_with_ueos

            packaged, ueos_extras = enrich_draft_with_ueos(
                packaged,
                runtime_dir=runtime_dir,
                editorial_category=editorial_category,
                quality_score=quality_score,
                is_breaking=is_breaking,
                publishing_mode=publishing_mode,
                cluster_size=cluster_size,
                cluster_texts=cluster_texts,
                newsroom_tz=newsroom_tz,
                layer_extras=dom_extras,
            )
            dom_extras = {**dom_extras, **ueos_extras}
    except Exception:
        pass

    try:
        from app.editorial.product_os.config import product_os_enabled

        if product_os_enabled():
            from app.editorial.product_os.peos_controller import enrich_draft_with_product_os

            packaged, peos_extras = enrich_draft_with_product_os(
                packaged,
                runtime_dir=runtime_dir,
                editorial_category=editorial_category,
                quality_score=quality_score,
                is_breaking=is_breaking,
                publishing_mode=publishing_mode,
                sources=sources,
                cluster_size=cluster_size,
                newsroom_tz=newsroom_tz,
                layer_extras=dom_extras,
            )
            dom_extras = {**dom_extras, **peos_extras}
    except Exception:
        pass

    try:
        from app.editorial.osgcp.config import osgcp_enabled

        if osgcp_enabled():
            from app.editorial.osgcp.controller import evaluate_osgcp

            packaged, osgcp_extras = evaluate_osgcp(
                packaged,
                runtime_dir=runtime_dir,
                publishing_mode=publishing_mode,
                quality_score=quality_score,
                cluster_size=cluster_size,
                cluster_texts=cluster_texts,
                newsroom_tz=newsroom_tz,
                layer_extras=dom_extras,
            )
            dom_extras = {**dom_extras, **osgcp_extras}
    except Exception:
        pass

    try:
        from app.editorial.ugsol.config import ugsol_enabled

        if ugsol_enabled():
            from app.editorial.ugsol.controller import run_ugsol_control_tower

            packaged, ugsol_extras = run_ugsol_control_tower(
                packaged,
                runtime_dir=runtime_dir,
                layer_extras=dom_extras,
                publishing_mode=publishing_mode,
                newsroom_tz=newsroom_tz,
                is_breaking=is_breaking,
            )
            dom_extras = {**dom_extras, **ugsol_extras}
    except Exception:
        pass

    try:
        from app.editorial.gmcs.config import gmcs_enabled

        if gmcs_enabled():
            from app.editorial.gmcs.controller import run_gmcs_competitive_analysis

            packaged, gmcs_extras = run_gmcs_competitive_analysis(
                packaged,
                runtime_dir=runtime_dir,
                layer_extras=dom_extras,
            )
            dom_extras = {**dom_extras, **gmcs_extras}
    except Exception:
        pass

    try:
        from app.editorial.eml.config import eml_enabled

        if eml_enabled():
            from app.editorial.eml.controller import enrich_with_editorial_monetization

            packaged, eml_extras = enrich_with_editorial_monetization(
                packaged,
                runtime_dir=runtime_dir,
                layer_extras=dom_extras,
                editorial_category=editorial_category,
                is_breaking=is_breaking,
            )
            dom_extras = {**dom_extras, **eml_extras}
    except Exception:
        pass

    try:
        from app.editorial.eaa.config import eaa_enabled

        if eaa_enabled():
            from app.editorial.eaa.controller import evaluate_editorial_autonomy_v2

            packaged, eaa_extras = evaluate_editorial_autonomy_v2(
                packaged,
                runtime_dir=runtime_dir,
                layer_extras=dom_extras,
                is_breaking=is_breaking,
                publishing_mode=publishing_mode,
                newsroom_tz=newsroom_tz,
            )
            dom_extras = {**dom_extras, **eaa_extras}
            dom_extras = _wire_beat_advisory_only(
                dom_extras, publishing_mode=publishing_mode, quality_score=quality_score
            )
            if eaa_extras.get("eaa_reject") and publishing_mode == "core":
                extras: dict[str, Any] = {
                    "editorial_stability": {
                        "publishing_mode": publishing_mode,
                        "growth_decision": decision.to_dict(),
                    },
                    **dom_extras,
                }
                return packaged, extras
    except Exception:
        pass

    if dom_extras.get("ugsol_reject") and publishing_mode == "core":
        dom_extras = _wire_beat_advisory_only(
            dom_extras, publishing_mode=publishing_mode, quality_score=quality_score
        )
        if dom_extras.get("ugsol_reject"):
            extras: dict[str, Any] = {
                "editorial_stability": {
                    "publishing_mode": publishing_mode,
                    "growth_decision": decision.to_dict(),
                },
                **dom_extras,
            }
            return packaged, extras

    if dom_extras:
        dom_extras = _wire_beat_advisory_only(
            dom_extras, publishing_mode=publishing_mode, quality_score=quality_score
        )
        extras: dict[str, Any] = {
            "editorial_stability": {
                "publishing_mode": publishing_mode,
                "growth_decision": decision.to_dict(),
            },
            **dom_extras,
        }
        return packaged, extras

    if decision.reject:
        dom = _wire_beat_advisory_only(
            {"growth_decision": decision.to_dict(), "stability_reject": True},
            publishing_mode=publishing_mode,
            quality_score=quality_score,
        )
        if dom.get("stability_reject"):
            return draft_body, dom

    packaged, pkg_meta = apply_editorial_packaging(
        draft_body,
        editorial_category=editorial_category,
        post_type=decision.post_type.value,
        include_share_cta=decision.retention_impact.value in {"viral", "habit"},
    )
    extras = {
        "editorial_stability": {
            "publishing_mode": publishing_mode,
            "growth_decision": decision.to_dict(),
            "packaging": pkg_meta,
        }
    }
    return packaged, extras


def content_hash_for_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sources_payload_for_synthesis(meta: dict[str, Any]) -> list[dict[str, Any]]:
    return [{"channel": "editorial_synthesis", "label": meta.get("synthesis_slot", "synthesis")}]


def note_stability_publish(runtime_dir: str | None, extras: dict[str, Any]) -> None:
    stab = extras.get("editorial_stability") if isinstance(extras.get("editorial_stability"), dict) else {}
    gd = stab.get("growth_decision") if isinstance(stab.get("growth_decision"), dict) else {}
    record_stability_publish(
        runtime_dir,
        post_type=str(gd.get("post_type") or "news"),
        publishing_mode=str(stab.get("publishing_mode") or "core"),
    )
    try:
        from app.editorial.growth_dominance.state import record_gravity_event

        dom = extras.get("editorial_dominance") if isinstance(extras.get("editorial_dominance"), dict) else {}
        grav = dom.get("gravity") if isinstance(dom.get("gravity"), dict) else {}
        loop_obj = dom.get("dominance_loop") if isinstance(dom.get("dominance_loop"), dict) else {}
        record_gravity_event(
            runtime_dir,
            gravity_total=float(grav.get("total") or 0),
            loop=str(loop_obj.get("loop") or "authority"),
            published=True,
        )
    except Exception:
        pass
    try:
        from app.editorial.audience_unification.state import record_auh_evaluation

        auh = extras.get("audience_unification") if isinstance(extras.get("audience_unification"), dict) else {}
        ues = auh.get("ues") if isinstance(auh.get("ues"), dict) else {}
        crs = auh.get("crs") if isinstance(auh.get("crs"), dict) else {}
        reader = auh.get("reader_simulation") if isinstance(auh.get("reader_simulation"), dict) else {}
        record_auh_evaluation(
            runtime_dir,
            ues=float(ues.get("total") or 0),
            crs=float(crs.get("total") or 0),
            reader_relevance=float(reader.get("reader_relevance_score") or 0),
            published=True,
        )
    except Exception:
        pass
    try:
        from app.editorial.unified_operating_system.state import record_ueos_decision

        ueos = extras.get("ueos") if isinstance(extras.get("ueos"), dict) else {}
        score = ueos.get("score") if isinstance(ueos.get("score"), dict) else {}
        repl = ueos.get("channel_replacement") if isinstance(ueos.get("channel_replacement"), dict) else {}
        arb = ueos.get("layer_arbitration") if isinstance(ueos.get("layer_arbitration"), dict) else {}
        record_ueos_decision(
            runtime_dir,
            ueos_total=float(score.get("total") or 0),
            action=str(ueos.get("decision") or "publish"),
            conflicts=list(arb.get("conflicts_resolved") or []),
            compression=bool((ueos.get("csim") or {}).get("applied")),
            replacement_score=int(repl.get("estimated_channels_replaced") or 0),
            published=True,
        )
    except Exception:
        pass
    try:
        from app.editorial.channel_product.state import record_channel_product_event

        cp = extras.get("channel_product") if isinstance(extras.get("channel_product"), dict) else {}
        loop = cp.get("growth_loop") if isinstance(cp.get("growth_loop"), dict) else {}
        viral = cp.get("viral_mechanics") if isinstance(cp.get("viral_mechanics"), dict) else {}
        cta = cp.get("cta_variant") if isinstance(cp.get("cta_variant"), dict) else {}
        record_channel_product_event(
            runtime_dir,
            loop_stage=str(loop.get("stage") or "reference_forward"),
            viral_tier=str(cp.get("viral_tier") or viral.get("viral_tier") or "standard"),
            cta_variant_id=str(cta.get("variant_id") or "general_v0"),
            reference_forward_score=float(cp.get("reference_forward_score") or viral.get("reference_forward_score") or 0),
            published=True,
        )
    except Exception:
        pass
    try:
        from app.editorial.product_os.state import record_peos_evaluation

        peos = extras.get("product_os") if isinstance(extras.get("product_os"), dict) else {}
        pg = peos.get("product_gravity") if isinstance(peos.get("product_gravity"), dict) else {}
        cse = peos.get("channel_substitution") if isinstance(peos.get("channel_substitution"), dict) else {}
        ref = peos.get("virality_v2") if isinstance(peos.get("virality_v2"), dict) else {}
        cta = peos.get("contextual_cta") if isinstance(peos.get("contextual_cta"), dict) else {}
        record_peos_evaluation(
            runtime_dir,
            pg_total=float(pg.get("total") or 0),
            substitution_score=float(cse.get("substitution_score") or 0),
            forward_prediction=float(ref.get("forward_prediction") or 0),
            cta_type=str(cta.get("cta_type") or "none"),
            content_format=str(peos.get("content_format") or "context"),
            published=True,
        )
    except Exception:
        pass
    try:
        from app.editorial.osgcp.state import record_osgcp_decision

        osgcp = extras.get("osgcp") if isinstance(extras.get("osgcp"), dict) else {}
        est = osgcp.get("editorial_state") if isinstance(osgcp.get("editorial_state"), dict) else {}
        dec = osgcp.get("editorial_decision") if isinstance(osgcp.get("editorial_decision"), dict) else {}
        cont = osgcp.get("continuity") if isinstance(osgcp.get("continuity"), dict) else {}
        record_osgcp_decision(
            runtime_dir,
            editorial_state=str(est.get("current_state") or "normal_state"),
            action=str(dec.get("action") or "publish"),
            format_mode=str(osgcp.get("format_mode") or "context"),
            continuity_triggered=bool(cont.get("triggered")),
            published=True,
        )
    except Exception:
        pass
    try:
        from app.editorial.ccd.state import record_ccd_evaluation

        ccd = extras.get("ccd") if isinstance(extras.get("ccd"), dict) else {}
        if not ccd:
            osgcp = extras.get("osgcp") if isinstance(extras.get("osgcp"), dict) else {}
            ccd = osgcp.get("ccd_evaluation") if isinstance(osgcp.get("ccd_evaluation"), dict) else {}
        binding = ccd.get("audience_reality_binding") if isinstance(ccd.get("audience_reality_binding"), dict) else {}
        spine = ccd.get("narrative_spine") if isinstance(ccd.get("narrative_spine"), dict) else {}
        record_ccd_evaluation(
            runtime_dir,
            category=str(ccd.get("category") or "macro"),
            experience_fit=float(ccd.get("experience_fit") or 0),
            binding_score=float(binding.get("binding_score") or 0),
            spine_matched=bool(spine.get("matched")),
            published=True,
        )
    except Exception:
        pass
    try:
        from app.editorial.mpaes.state import record_mpaes_evaluation

        mpaes = extras.get("mpaes") if isinstance(extras.get("mpaes"), dict) else {}
        if mpaes:
            hub = mpaes.get("hub_substitution") if isinstance(mpaes.get("hub_substitution"), dict) else {}
            record_mpaes_evaluation(
                runtime_dir,
                dual_audience_trust=float(mpaes.get("dual_audience_trust") or 0),
                hub_substitution_score=float(hub.get("substitution_score") or 0),
                vertical=str(hub.get("vertical") or "macro"),
                published=True,
            )
    except Exception:
        pass
    try:
        from app.editorial.ugsol.state import record_control_tower_decision

        ugsol = extras.get("ugsol") if isinstance(extras.get("ugsol"), dict) else {}
        final = extras.get("final_editorial_decision") if isinstance(extras.get("final_editorial_decision"), dict) else {}
        if not final:
            final = ugsol.get("final_decision") if isinstance(ugsol.get("final_decision"), dict) else {}
        imri = ugsol.get("imri") if isinstance(ugsol.get("imri"), dict) else {}
        obj = ugsol.get("system_objective") if isinstance(ugsol.get("system_objective"), dict) else {}
        if final:
            record_control_tower_decision(
                runtime_dir,
                publish=bool(final.get("publish")),
                mode=str(final.get("mode") or "context"),
                priority_level=str(final.get("priority_level") or "normal"),
                imri_score=float(imri.get("score") or 0),
                objective_score=float(obj.get("composite_score") or 0),
                published=True,
            )
    except Exception:
        pass
    try:
        from app.editorial.gmcs.state import record_gmcs_evaluation

        gmcs = extras.get("gmcs") if isinstance(extras.get("gmcs"), dict) else {}
        dom = gmcs.get("market_dominance") if isinstance(gmcs.get("market_dominance"), dict) else {}
        sim = gmcs.get("ecosystem_simulation") if isinstance(gmcs.get("ecosystem_simulation"), dict) else {}
        if gmcs:
            record_gmcs_evaluation(
                runtime_dir,
                mdi=float(dom.get("index") or 0),
                channels_substituted=int(sim.get("channels_substituted_estimate") or 0),
                vertical=str(sim.get("vertical") or "macro"),
                published=True,
            )
    except Exception:
        pass
    try:
        from app.editorial.eml.state import record_eml_evaluation

        eml = extras.get("eml") if isinstance(extras.get("eml"), dict) else {}
        attn = eml.get("attention_value") if isinstance(eml.get("attention_value"), dict) else {}
        rev = eml.get("revenue_abstraction") if isinstance(eml.get("revenue_abstraction"), dict) else {}
        gate = eml.get("monetization_gate") if isinstance(eml.get("monetization_gate"), dict) else {}
        if eml:
            record_eml_evaluation(
                runtime_dir,
                cognitive_value=float(attn.get("cognitive_value_score") or 0),
                value_index=float(rev.get("estimated_value_index") or 0),
                monetization_allowed=bool(gate.get("allow_monetization")),
                published=True,
            )
    except Exception:
        pass
    try:
        from app.editorial.eaa.state import record_eaa_decision

        eaa = extras.get("eaa") if isinstance(extras.get("eaa"), dict) else {}
        aut = eaa.get("autonomy_decision") if isinstance(eaa.get("autonomy_decision"), dict) else {}
        if eaa:
            record_eaa_decision(
                runtime_dir,
                mode=str(aut.get("mode") or "human_required"),
                autonomous_publish=bool(aut.get("autonomous_publish")),
                confidence=float(aut.get("confidence") or 0),
                published=True,
            )
    except Exception:
        pass


def merge_stability_extras_json(existing: str | None, patch: dict[str, Any]) -> str:
    base: dict[str, Any] = {}
    if existing:
        try:
            base = json.loads(existing)
            if not isinstance(base, dict):
                base = {}
        except (json.JSONDecodeError, TypeError):
            base = {}
    base.update(patch)
    return json.dumps(base, ensure_ascii=False)
