from __future__ import annotations

from pathlib import Path
from typing import Any

from bot.storage.db import default_db_path, init_database


def collect_operational_context(
    *,
    db_path: Path | None = None,
    base_url: str = "http://127.0.0.1:8080",
    pulse: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Gather signals for digest, dashboard, and attention queue. Fail-open."""
    path = init_database(db_path or default_db_path())
    ctx: dict[str, Any] = {"db_path": str(path)}

    try:
        if pulse is None:
            from bot.ops_observation.collector import collect_observation_pulse

            pulse = collect_observation_pulse(base_url=base_url, db_path=str(path))
        ctx["pulse"] = pulse
    except Exception:
        ctx["pulse"] = {}

    try:
        from bot.editorial.priority.service import build_ranked_queue, get_priority_repo
        from bot.editorial.priority.drift import analyze_priority_drift

        ranked, meta = build_ranked_queue(limit=8, db_path=path)
        ctx["priority_queue"] = ranked
        ctx["priority_drift"] = meta.get("drift") or analyze_priority_drift(
            get_priority_repo(path).recent_scores(hours=72),
        )
    except Exception:
        ctx["priority_queue"] = []
        ctx["priority_drift"] = {}

    try:
        from bot.editorial.memory.service import get_editorial_memory_repo

        mem = get_editorial_memory_repo(path)
        ctx["active_storylines"] = [
            {
                "storyline_id": s.storyline_id,
                "title": s.title,
                "publish_count": s.publish_count,
                "saturation": s.saturation_score,
            }
            for s in mem.active_storylines(limit=8)
        ]
    except Exception:
        ctx["active_storylines"] = []

    try:
        from bot.live_ops.repository import LiveChannelRepository

        live = LiveChannelRepository(path)
        ctx["live_incidents"] = live.recent_incidents(limit=8)
        ctx["publish_success_rate"] = live.publish_success_rate()
        state = live.get_state() or {}
        ctx["live_state"] = state
    except Exception:
        ctx["live_incidents"] = []
        ctx["publish_success_rate"] = None
        ctx["live_state"] = {}

    try:
        from bot.operator_ux.repository import AttentionMetricsRepository

        ctx["noise_metrics"] = AttentionMetricsRepository(path).noise_metrics(hours=24)
    except Exception:
        ctx["noise_metrics"] = {}

    stats = (ctx.get("pulse") or {}).get("publish_stats_24h") or {}
    ctx["publish_stats"] = stats

    try:
        from bot.ops_consolidation.service import maybe_dedupe_operator_context

        ctx = maybe_dedupe_operator_context(ctx)
    except Exception:
        pass

    try:
        from bot.editorial.flow_health.service import flow_health_snapshot

        fh = flow_health_snapshot(db_path=path)
        ctx["publish_funnel"] = fh.get("funnel")
        ctx["flow_adaptive"] = fh.get("adaptive")
        ctx["flow_coverage"] = fh.get("coverage")
        ctx["flow_trends"] = fh.get("trends")
        ctx["flow_cadence"] = fh.get("cadence")
        ctx["flow_canary"] = fh.get("canary_balance")
        ctx["publish_floor_active"] = fh.get("publish_floor_active")
        ctx["duplicate_escapes_24h"] = fh.get("duplicate_escapes_24h", 0)
        ctx["duplicate_escapes_72h"] = fh.get("duplicate_escapes_72h", 0)
        cal = fh.get("calibration") or {}
        ctx["flow_calibration"] = cal
        ctx["newsroom_mode"] = (cal.get("newsroom_mode") or {}).get("current_mode")
        ctx["predictability_score"] = (cal.get("predictability") or {}).get(
            "predictability_score",
        )
        gov = fh.get("governance") or {}
        ctx["flow_governance"] = gov
        trust = gov.get("trust_index") or {}
        ctx["operator_trust_index"] = trust.get("operator_trust_index")
        ctx["operator_trust_band"] = trust.get("operator_trust_band")
    except Exception:
        pass

    try:
        from bot.editorial.flow_health.governance import enrich_governance_with_cockpit

        ctx["flow_governance"] = enrich_governance_with_cockpit(ctx)
        gov = ctx["flow_governance"] or {}

        trust = gov.get("trust_index") or {}
        ctx["operator_trust_index"] = trust.get("operator_trust_index")
        ctx["operator_trust_band"] = trust.get("operator_trust_band")
        vit = gov.get("vitality") or {}
        real = vit.get("realism") or {}
        ctx["operational_realism_index"] = real.get("operational_realism_index")
        ctx["editorial_vitality_score"] = (vit.get("vitality") or {}).get(
            "editorial_vitality_score",
        )
        dur = gov.get("durability") or {}
        ctx["flow_durability"] = dur
        ctx["degradation_mode"] = (gov.get("degradation") or {}).get("mode")
        sim = dur.get("simplicity") or {}
        ctx["operational_simplicity_index"] = sim.get("operational_simplicity_index")
        ctx["flow_slimming"] = gov.get("slimming") or {}
        rel = gov.get("reliability") or {}
        ctx["flow_reliability"] = rel
        mat = rel.get("operational_maturity") or {}
        ctx["operational_maturity_index"] = mat.get("operational_maturity_index")
        ctx["flow_rehearsal"] = gov.get("rehearsal") or {}
        freeze = ctx["flow_rehearsal"].get("core_freeze") or {}
        ctx["core_freeze_candidate"] = freeze.get("core_freeze_candidate")
        ctx["flow_certification"] = gov.get("certification") or {}
        cert = ctx["flow_certification"]
        ctx["operational_confidence_index"] = (cert.get("operational_confidence") or {}).get(
            "operational_confidence_index",
        )
        ctx["operational_confidence_band"] = (cert.get("operational_confidence") or {}).get(
            "operational_confidence_band",
        )
        ctx["maintenance_mode_ready"] = (cert.get("maintenance_mode") or {}).get("maintenance_mode_ready")
        ctx["operational_certification_candidate"] = (cert.get("operational_certification") or {}).get(
            "operational_certification_candidate",
        )
        frz = gov.get("freeze_registry") or {}
        ctx["flow_freeze_registry"] = frz
        ctx["drift_exposure_index"] = (frz.get("drift_exposure") or {}).get("drift_exposure_index")
        ctx["drift_exposure_band"] = (frz.get("drift_exposure") or {}).get("drift_exposure_band")
        ctx["stewardship_horizon_days"] = (frz.get("stewardship_horizon") or {}).get("stewardship_horizon_days")
        ctx["stewardship_horizon_band"] = (frz.get("stewardship_horizon") or {}).get("stewardship_horizon_band")
        ctx["ultra_quiet_digest"] = frz.get("ultra_quiet_digest")
        omem = gov.get("operational_memory") or {}
        ctx["flow_operational_memory"] = omem
        ctx["institutional_calmness_index"] = omem.get("institutional_calmness_index")
        ctx["institutional_calmness_band"] = omem.get("institutional_calmness_band")
        ctx["recurrence_detected"] = omem.get("recurrence_detected")
        ctx["historical_recovery_mode"] = omem.get("historical_recovery_mode")
        ctx["operational_memory_active"] = omem.get("operational_memory_active")
        doc = gov.get("doctrine") or {}
        ctx["flow_doctrine"] = doc
        ctx["stewardship_constitution_score"] = doc.get("stewardship_constitution_score")
        ctx["stewardship_constitution_band"] = doc.get("stewardship_constitution_band")
        ctx["doctrine_drift_detected"] = doc.get("doctrine_drift_detected")
        ctx["institutional_stewardship_mode"] = doc.get("institutional_stewardship_mode")
        ctx["doctrine_alignment_status"] = doc.get("doctrine_alignment_status")
        sres = gov.get("strategic_resilience") or {}
        ctx["flow_strategic_resilience"] = sres
        ctx["strategic_resilience_index"] = sres.get("strategic_resilience_index")
        ctx["strategic_resilience_band"] = sres.get("strategic_resilience_band")
        ctx["sustainability_horizon_days"] = sres.get("sustainability_horizon_days")
        ctx["sustainability_horizon_band"] = sres.get("sustainability_horizon_band")
        ctx["architectural_erosion_detected"] = sres.get("architectural_erosion_detected")
        ctx["stewardship_fatigue_detected"] = sres.get("stewardship_fatigue_detected")
        ctx["long_horizon_sustainability"] = sres.get("long_horizon_sustainability")
        min_gov = gov.get("minimalism") or {}
        ctx["flow_minimalism"] = min_gov
        ctx["architectural_compression_score"] = min_gov.get("architectural_compression_score")
        ctx["architectural_compression_band"] = min_gov.get("architectural_compression_band")
        ctx["operational_entropy_accumulation"] = min_gov.get("operational_entropy_accumulation")
        ctx["quiet_infrastructure_streak_days"] = min_gov.get("quiet_infrastructure_streak_days")
        ctx["compression_candidates_count"] = min_gov.get("compression_candidates_count")
        clos = gov.get("closure") or {}
        ctx["flow_closure"] = clos
        ctx["governance_saturation_index"] = clos.get("governance_saturation_index")
        ctx["governance_saturation_band"] = clos.get("governance_saturation_band")
        ctx["architectural_sufficiency"] = clos.get("architectural_sufficiency")
        ctx["expansion_pressure_detected"] = clos.get("expansion_pressure_detected")
        ctx["steady_state_streak_days"] = clos.get("steady_state_streak_days")
        ctx["operational_closure_candidate"] = clos.get("operational_closure_candidate")
        leg = gov.get("legacy") or {}
        ctx["flow_legacy"] = leg
        ctx["stewardship_dependency_risk"] = leg.get("stewardship_dependency_risk")
        ctx["operational_legibility_index"] = leg.get("operational_legibility_index")
        ctx["operational_legibility_band"] = leg.get("operational_legibility_band")
        ctx["succession_readiness"] = leg.get("succession_readiness")
        ctx["institutional_transferability_band"] = leg.get("institutional_transferability_band")
        try:
            from bot.editorial.flow_health.observability import observability_snapshot

            obs = observability_snapshot(ctx=ctx, governance=gov, collector_ctx=ctx)
            gov["observability"] = obs
            ctx["flow_observability"] = obs
            ctx["governance_cohesion_status"] = obs.get("governance_cohesion_status")
            ctx["observability_integrity_index"] = obs.get("observability_integrity_index")
            ctx["observability_integrity_band"] = obs.get("observability_integrity_band")
            ctx["observability_drift_detected"] = obs.get("observability_drift_detected")
            ctx["canonical_truth_streak_days"] = obs.get("canonical_truth_streak_days")
        except Exception:
            pass
        try:
            from bot.editorial.flow_health.convergence import convergence_snapshot

            conv = convergence_snapshot(ctx=ctx, governance=gov)
            gov["convergence"] = conv
            ctx["flow_convergence"] = conv
            ctx["governance_converged"] = conv.get("governance_converged")
            ctx["stewardship_recursion_detected"] = conv.get("stewardship_recursion_detected")
            ctx["governance_finalization_index"] = conv.get("governance_finalization_index")
            ctx["governance_finalization_band"] = conv.get("governance_finalization_band")
            ctx["stewardship_novelty_decay"] = conv.get("stewardship_novelty_decay")
            ctx["governance_convergence_streak_days"] = conv.get("governance_convergence_streak_days")
            ctx["governance_finalization_candidate"] = conv.get("governance_finalization_candidate")
        except Exception:
            pass
    except Exception:
        pass

    return ctx
