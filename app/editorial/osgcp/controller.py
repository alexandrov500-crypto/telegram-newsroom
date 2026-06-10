"""OSGCP controller — final operational control plane."""

from __future__ import annotations

import hashlib
from typing import Any

from app.editorial.osgcp.arbitration_engine import EditorialAction, EditorialDecision, FormatMode, arbitrate_editorial_decision
from app.editorial.osgcp.attention_buffer import record_attention_cluster
from app.editorial.osgcp.config import osgcp_enabled
from app.editorial.osgcp.continuity_controller import evaluate_continuity
from app.editorial.osgcp.kpi_loop import compute_editorial_kpi_state
from app.editorial.osgcp.mode_oscillator import evaluate_mode_oscillation
from app.editorial.osgcp.state import load_state, record_osgcp_decision
from app.editorial.osgcp.state_machine import resolve_editorial_state
from app.editorial.stability.anti_pause import evaluate_anti_pause
from app.editorial.stability.slo import stability_slo_snapshot


def _extract(layer: dict[str, Any], *keys: str, default: float = 0.0) -> float:
    cur: Any = layer
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k)
    try:
        return float(cur)
    except (TypeError, ValueError):
        return default


def evaluate_osgcp(
    body: str,
    *,
    runtime_dir: str | None,
    publishing_mode: str,
    quality_score: float,
    cluster_size: int = 1,
    cluster_texts: list[str] | None = None,
    newsroom_tz: str = "Europe/Moscow",
    layer_extras: dict[str, Any] | None = None,
    cluster_fingerprint: str = "",
) -> tuple[str, dict[str, Any]]:
    if not osgcp_enabled():
        return body, {}

    layer_extras = layer_extras or {}
    ap = evaluate_anti_pause(newsroom_tz=newsroom_tz)
    slo = stability_slo_snapshot(runtime_dir, newsroom_tz=newsroom_tz)
    slo_inner = slo.get("slo") if isinstance(slo.get("slo"), dict) else {}

    pg = _extract(layer_extras, "product_os", "product_gravity", "total")
    gravity = _extract(layer_extras, "editorial_dominance", "gravity", "total", default=50.0)
    crs = _extract(layer_extras, "audience_unification", "crs", "total", default=50.0)
    src_indep = _extract(layer_extras, "editorial_dominance", "source_graph", "independence_score", default=0.75)
    continuity = float(slo_inner.get("continuity_score") or 0.75)
    gap_min = ap.publish_gap_minutes

    grav_avg = gravity
    try:
        from app.editorial.growth_dominance.state import today_gravity_stats

        grav_avg = float(today_gravity_stats(runtime_dir).get("avg_gravity") or gravity)
    except Exception:
        pass

    desk_streak = int(load_state(runtime_dir).get("desk_rejects_streak") or 0)

    editorial_state = resolve_editorial_state(
        gravity_avg=grav_avg,
        gap_minutes=gap_min,
        desk_rejects_consecutive=desk_streak,
        publishing_mode=publishing_mode,
        anti_pause_active=ap.anti_pause_active,
    )

    peos_reject = bool(layer_extras.get("product_os_reject"))
    ueos_reject = bool(layer_extras.get("stability_reject") or layer_extras.get("ueos_reject"))

    decision = arbitrate_editorial_decision(
        editorial_state=editorial_state.current_state,
        pg_total=pg or quality_score,
        gravity_total=gravity,
        crs_total=crs,
        continuity_score=continuity,
        source_independence=src_indep,
        gap_minutes=gap_min,
        peos_reject=peos_reject,
        ueos_reject=ueos_reject,
        publishing_mode=publishing_mode,
    )

    cse_sub = _extract(layer_extras, "product_os", "channel_substitution", "substitution_score", default=pg or quality_score)
    mpaes_eval: dict[str, Any] = layer_extras.get("mpaes") if isinstance(layer_extras.get("mpaes"), dict) else {}
    if not mpaes_eval:
        try:
            from app.editorial.mpaes.controller import evaluate_mpaes_state

            mpaes_eval = evaluate_mpaes_state(
                body,
                runtime_dir=runtime_dir,
                editorial_category=str(
                    (layer_extras.get("product_os") or {}).get("editorial_category", "")
                    if isinstance(layer_extras.get("product_os"), dict)
                    else ""
                ),
                sources=list(layer_extras.get("sources") or []) if isinstance(layer_extras.get("sources"), list) else [],
                cluster_size=cluster_size,
                is_breaking=bool(layer_extras.get("priority_boost")),
                newsroom_tz=newsroom_tz,
                publishing_mode=publishing_mode,
                substitution_score=cse_sub,
            )
        except Exception:
            mpaes_eval = {"enabled": False}

    decision_dict_pre_ccd = decision.to_dict()
    try:
        from app.editorial.mpaes.controller import apply_mpaes_to_decision

        decision_dict_pre_ccd = apply_mpaes_to_decision(
            decision_dict_pre_ccd,
            {"mpaes": mpaes_eval},
            publishing_mode=publishing_mode,
        )
        decision = EditorialDecision(
            action=EditorialAction(decision_dict_pre_ccd["action"]),
            format_mode=FormatMode(decision_dict_pre_ccd["format_mode"]),
            override_source=decision.override_source,
            reasoning_trace=tuple(decision_dict_pre_ccd.get("reasoning_trace") or []),
            force_digest=bool(decision_dict_pre_ccd.get("force_digest")),
            priority_boost=bool(decision_dict_pre_ccd.get("priority_boost")),
            stability_override=bool(decision_dict_pre_ccd.get("stability_override")),
            reject=bool(decision_dict_pre_ccd.get("reject")),
        )
    except Exception:
        pass

    ccd_eval: dict[str, Any] = {"enabled": False}
    try:
        from app.editorial.ccd.controller import apply_ccd_to_decision, evaluate_weekly_experience_state

        ccd_eval = evaluate_weekly_experience_state(
            body,
            runtime_dir=runtime_dir,
            editorial_category=str(
                (layer_extras.get("product_os") or {}).get("editorial_category", "")
                if isinstance(layer_extras.get("product_os"), dict)
                else ""
            ),
            gravity=gravity,
            substitution_score=cse_sub,
            is_breaking=bool(layer_extras.get("priority_boost")),
            newsroom_tz=newsroom_tz,
        )
        decision_dict = apply_ccd_to_decision(decision_dict_pre_ccd, ccd_eval, publishing_mode=publishing_mode)
        decision = EditorialDecision(
            action=EditorialAction(decision_dict["action"]),
            format_mode=FormatMode(decision_dict["format_mode"]),
            override_source=decision.override_source,
            reasoning_trace=tuple(decision_dict.get("reasoning_trace") or []),
            force_digest=bool(decision_dict.get("force_digest")),
            priority_boost=bool(decision_dict.get("priority_boost")),
            stability_override=bool(decision_dict.get("stability_override")),
            reject=bool(decision_dict.get("reject")),
        )
    except Exception:
        pass

    oscillation = evaluate_mode_oscillation(runtime_dir, proposed_format=decision.format_mode)
    final_format = oscillation.suggested_format if not oscillation.allowed else decision.format_mode
    if ccd_eval.get("enabled") and ccd_eval.get("force_digest"):
        final_format = FormatMode.DIGEST

    can_publish = decision.action in {
        EditorialAction.PUBLISH,
        EditorialAction.PRIORITY_BOOST,
    } and not decision.reject

    continuity = evaluate_continuity(
        runtime_dir=runtime_dir,
        gap_minutes=gap_min,
        pg_total=pg or quality_score,
        gravity_total=gravity,
        crs_total=crs,
        can_publish=can_publish,
    )

    if continuity.triggered and not can_publish and not decision.reject:
        decision = arbitrate_editorial_decision(
            editorial_state=editorial_state.current_state,
            pg_total=max(pg, 55.0),
            gravity_total=gravity,
            crs_total=crs,
            continuity_score=0.35,
            source_independence=src_indep,
            gap_minutes=gap_min,
            peos_reject=False,
            ueos_reject=False,
            publishing_mode="elastic_fill" if ap.anti_pause_active else publishing_mode,
        )
        final_format = FormatMode.DIGEST

    fp = cluster_fingerprint or hashlib.sha256((body or "").encode("utf-8")).hexdigest()[:16]
    if cluster_texts:
        combined = "\n".join(cluster_texts[:5])
        record_attention_cluster(
            runtime_dir,
            fingerprint=fp,
            combined_text=combined or body,
            quality_score=quality_score,
        )
    elif body:
        record_attention_cluster(
            runtime_dir,
            fingerprint=fp,
            combined_text=body,
            quality_score=quality_score,
        )

    kpi = compute_editorial_kpi_state(runtime_dir)

    record_osgcp_decision(
        runtime_dir,
        editorial_state=editorial_state.current_state.value,
        action=decision.action.value,
        format_mode=final_format.value,
        continuity_triggered=continuity.triggered,
        published=False,
    )

    out: dict[str, Any] = {
        "osgcp": {
            "editorial_state": editorial_state.to_dict(),
            "editorial_decision": decision.to_dict(),
            "format_mode": final_format.value,
            "mode_oscillation": oscillation.to_dict(),
            "continuity": continuity.to_dict(),
            "kpi_state": kpi.to_dict(),
            "anti_pause": ap.to_dict(),
            "objective": "adaptive_cognitive_information_os_continuous_flow",
            "shipping_authority": "osgcp_advisory",
            "final_authority": "ugsol_control_tower",
            "arbitration_order": [
                "continuity",
                "peos",
                "egdl",
                "auh",
                "mpaes",
                "ccd",
                "publish",
            ],
            "mpaes_evaluation": mpaes_eval,
            "ccd_evaluation": ccd_eval,
        }
    }

    if mpaes_eval.get("enabled"):
        out["mpaes"] = mpaes_eval
    if ccd_eval.get("enabled"):
        out["ccd"] = ccd_eval

    if decision.reject and publishing_mode == "core" and not decision.stability_override:
        out["osgcp_reject"] = True
    else:
        out.pop("product_os_reject", None)
        out.pop("ueos_reject", None)
        out.pop("osgcp_reject", None)

    if decision.force_digest or final_format == FormatMode.DIGEST:
        out["force_digest_slot"] = True
    if decision.priority_boost or decision.action == EditorialAction.PRIORITY_BOOST:
        out["priority_boost"] = True
    if decision.action == EditorialAction.SYNTHESIZE or continuity.mode_used.startswith("synthesis"):
        out["osgcp_synthesize"] = True
        out["force_digest_slot"] = True

    return body, out
