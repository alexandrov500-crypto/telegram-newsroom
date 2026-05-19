from __future__ import annotations

import html
import os
from typing import Any

from bot.editorial.flow_health.warning_fatigue import process_warnings


def _collect_raw_warnings(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    flow = ctx.get("publish_funnel") or {}
    starve = flow.get("starvation") or {}
    if starve.get("detected"):
        warnings.append(
            {
                "tier": "WARNING",
                "category": "starvation",
                "message": f"Publish starvation: {starve.get('reason', '?')}",
            },
        )

    trends = ctx.get("flow_trends") or {}
    if trends.get("permissive_drift_warning"):
        warnings.append(
            {
                "tier": "WARNING",
                "category": "drift",
                "message": str(trends.get("drift_interpretation", "Permissive drift")),
            },
        )

    cal = ctx.get("flow_calibration") or {}
    thr = cal.get("threshold_stability") or {}
    if thr.get("threshold_stability_warning"):
        warnings.append(
            {
                "tier": "WARNING",
                "category": "threshold",
                "message": "Relaxation budget near saturation",
            },
        )

    gov = ctx.get("flow_governance") or {}
    baseline = gov.get("baseline") or {}
    if baseline.get("drift_detected"):
        warnings.append(
            {
                "tier": "WARNING",
                "category": "baseline",
                "message": f"Long-window calibration drift ({baseline.get('baseline_deviation')})",
            },
        )

    trust = gov.get("trust_index") or {}
    if trust.get("metric_illusion_risk"):
        warnings.append(
            {
                "tier": "NOTICE",
                "category": "trust",
                "message": "Predictability healthy but diversity/drift lagging",
            },
        )

    cfg = gov.get("config_pressure") or {}
    if cfg.get("configuration_pressure_band") == "high":
        warnings.append(
            {
                "tier": "NOTICE",
                "category": "config",
                "message": f"Configuration pressure elevated ({cfg.get('configuration_pressure_score')})",
            },
        )

    pulse = ctx.get("pulse") or {}
    if float(pulse.get("event_loop_lag_max") or 0) > 2.0:
        warnings.append(
            {
                "tier": "CRITICAL",
                "category": "runtime",
                "message": f"Event loop lag {pulse.get('event_loop_lag_max')}s",
            },
        )

    dup = int(ctx.get("duplicate_escapes_24h") or 0)
    if dup > 0:
        warnings.append(
            {
                "tier": "WARNING",
                "category": "duplicate",
                "message": f"Duplicate escape events: {dup} (24h)",
            },
        )

    deg = gov.get("degradation") or (gov.get("durability") or {}).get("degradation") or {}
    if deg.get("mode") not in (None, "NORMAL"):
        warnings.append(
            {
                "tier": "NOTICE",
                "category": "degradation",
                "message": f"Degradation mode {deg.get('mode')}: {', '.join(deg.get('reasons') or [])[:60]}",
            },
        )

    dig = cal.get("digest_discipline") or {}
    if dig.get("digest_heavy"):
        warnings.append(
            {
                "tier": "NOTICE",
                "category": "digest",
                "message": "Recovery digests dominating output",
            },
        )

    vit_gov = gov.get("vitality") or {}
    stag = vit_gov.get("stagnation") or {}
    if stag.get("stagnation_risk") == "HIGH":
        warnings.append(
            {
                "tier": "WARNING",
                "category": "stagnation",
                "message": "Editorial stagnation risk elevated",
            },
        )
    elif stag.get("stagnation_risk") == "MODERATE":
        warnings.append(
            {
                "tier": "NOTICE",
                "category": "stagnation",
                "message": "Editorial vitality muted — watch for narrowing",
            },
        )

    vit = vit_gov.get("vitality") or {}
    if vit.get("vitality_band") == "stale":
        warnings.append(
            {
                "tier": "WARNING",
                "category": "vitality",
                "message": f"Low editorial vitality ({vit.get('editorial_vitality_score')})",
            },
        )

    real = vit_gov.get("realism") or {}
    if not real.get("living_newsroom") and float(real.get("operational_realism_index") or 1) < 0.55:
        warnings.append(
            {
                "tier": "NOTICE",
                "category": "realism",
                "message": "Operational realism below living-newsroom threshold",
            },
        )

    return warnings


def build_cockpit_summary(ctx: dict[str, Any]) -> dict[str, Any]:
    """Compressed operational lines for digest — cockpit style."""
    gov = ctx.get("flow_governance") or {}
    cal = ctx.get("flow_calibration") or {}
    mode = (cal.get("newsroom_mode") or {}).get("current_mode", "STABLE")
    trust = gov.get("trust_index") or {}
    baseline = gov.get("baseline") or {}
    windows = baseline.get("windows") or {}
    surge = gov.get("surge") or {}

    bullets: list[str] = []
    dev_7d = float(windows.get("7d") or baseline.get("baseline_deviation") or 0)
    if dev_7d < 0.12 and mode == "STABLE":
        bullets.append("Stable for 72h — no significant drift detected")
    elif baseline.get("drift_detected"):
        bullets.append(f"Calibration drift trending ({dev_7d:.2f} vs 7d baseline)")
    else:
        bullets.append(f"Mode {mode} — baseline deviation {dev_7d:.2f}")

    cat = cal.get("category_balance") or {}
    if cat.get("imbalanced"):
        bullets.append(
            f"Minor category imbalance: {cat.get('dominant_bucket')} dominant "
            f"({float(cat.get('dominant_ratio') or 0):.0%})",
        )

    dig = cal.get("digest_discipline") or {}
    if float(dig.get("digest_to_publish_ratio") or 0) < 0.15 and int(
        dig.get("consecutive_digest_recoveries") or 0,
    ) == 0:
        bullets.append("Digest dependency resolved")
    elif dig.get("digest_heavy"):
        bullets.append("Digest dependency elevated — prefer individual stories")

    cfg = gov.get("config_pressure") or {}
    band = cfg.get("configuration_pressure_band", "low")
    if band != "low":
        bullets.append(f"Configuration pressure {band} ({cfg.get('configuration_pressure_score')})")
    else:
        bullets.append("Configuration pressure low")

    if surge.get("surge_active"):
        bullets.append("Breaking-news surge — rhythm smoothing relaxed")

    vit_gov = gov.get("vitality") or {}
    vit = vit_gov.get("vitality") or {}
    real = vit_gov.get("realism") or {}
    if vit:
        bullets.append(
            f"Vitality {vit.get('editorial_vitality_score', '—')} · "
            f"realism {real.get('operational_realism_index', '—')} ({real.get('operational_realism_band', '?')})",
        )
    stag = vit_gov.get("stagnation") or {}
    if stag.get("stagnation_risk") not in (None, "LOW"):
        bullets.append(f"Stagnation risk {stag.get('stagnation_risk')}")
    elif vit_gov.get("freshness_trend") == "healthy":
        bullets.append("Editorial freshness healthy")

    np = vit_gov.get("novelty_pressure") or {}
    if float(np.get("novelty_pressure_score") or 0) >= 0.55:
        bullets.append("Novelty pressure elevated — many posts, low freshness")

    lt = vit_gov.get("longtail") or {}
    if int(lt.get("longtail_publish_count") or 0) > 0:
        bullets.append(
            f"Long-tail activity {float(lt.get('longtail_share') or 0):.0%} of recent publishes",
        )

    resp = vit_gov.get("responsiveness") or {}
    if resp.get("medium_cycle_active"):
        bullets.append("Medium-cycle responsiveness — evolving story clusters")

    dur = gov.get("durability") or {}
    infl = dur.get("influences") or {}
    if infl.get("influence_summary"):
        bullets.append("Influences: " + ", ".join(infl["influence_summary"][:3]))
    for audit in dur.get("self_audit_bullets") or []:
        bullets.append(str(audit)[:100])
    immune = dur.get("baseline_immunity") or {}
    if immune.get("immunity_active"):
        bullets.append("Baseline immunity: resisting normalized degradation")

    raw = _collect_raw_warnings(ctx)
    active = process_warnings(raw)
    warning_pressure = min(1.0, len(raw) / 8.0)

    clarity = 1.0
    if len(active) > 4:
        clarity = 0.65
    elif len(active) > 2:
        clarity = 0.82

    try:
        from bot.editorial.flow_health.slimming.telemetry_prune import prune_cockpit_bullets

        pruned = prune_cockpit_bullets(bullets, ctx)
        bullets = pruned.get("bullets") or bullets
    except Exception:
        pruned = {"pruned_count": 0, "pruning_active": False}

    density_meta: dict = {}
    try:
        from bot.editorial.flow_health.reliability.telemetry_density import (
            apply_collapse_protection,
            measure_telemetry_density,
        )

        density_meta = measure_telemetry_density(cockpit={"cockpit_bullets": bullets, **cockpit}, ctx=ctx)
        bullets = apply_collapse_protection(bullets, density_meta)
    except Exception:
        pass

    return {
        "cockpit_bullets": bullets[:8],
        "active_warnings": active,
        "warning_pressure": round(warning_pressure, 3),
        "digest_clarity": round(clarity, 3),
        "compression_enabled": _compression_enabled(),
        "telemetry_prune": pruned,
        "telemetry_density": density_meta,
    }


def _compression_enabled() -> bool:
    return os.getenv("DIGEST_SIGNAL_COMPRESSION", "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def format_compressed_digest_html(ctx: dict[str, Any]) -> list[str]:
    """HTML lines for compressed cockpit section."""
    cockpit = build_cockpit_summary(ctx)
    gov = ctx.get("flow_governance") or {}
    trust = gov.get("trust_index") or {}
    dur = gov.get("durability") or ctx.get("flow_durability") or {}
    rehe = gov.get("rehearsal") or ctx.get("flow_rehearsal") or {}
    cert = gov.get("certification") or ctx.get("flow_certification") or {}
    frz = gov.get("freeze_registry") or ctx.get("flow_freeze_registry") or {}
    omem = gov.get("operational_memory") or ctx.get("flow_operational_memory") or {}
    doc = gov.get("doctrine") or ctx.get("flow_doctrine") or {}
    sres = gov.get("strategic_resilience") or ctx.get("flow_strategic_resilience") or {}
    min_gov = gov.get("minimalism") or ctx.get("flow_minimalism") or {}
    closure_gov = gov.get("closure") or ctx.get("flow_closure") or {}
    rel = gov.get("reliability") or ctx.get("flow_reliability") or {}
    mat = rel.get("operational_maturity") or {}
    conf = cert.get("operational_confidence") or {}
    exp = frz.get("drift_exposure") or {}
    horizon = frz.get("stewardship_horizon") or {}
    memory_lines = list(omem.get("memory_stewardship_lines") or [])
    stewardship = list(frz.get("stewardship_summary_lines") or cert.get("stewardship_summary_lines") or [])
    exec_lines = list(rehe.get("executive_summary_lines") or [])
    show_stewardship = bool(stewardship) or mat.get("long_run_safe") or mat.get("operational_maturity_index", 0) >= 0.68
    ultra_quiet = bool(frz.get("ultra_quiet_digest"))
    institutional = bool(doc.get("institutional_stewardship_mode"))
    doctrine_lines = list(doc.get("doctrine_digest_lines") or [])
    resilience_lines = list(sres.get("resilience_digest_lines") or [])
    long_horizon = bool(sres.get("long_horizon_sustainability"))
    minimalism_lines = list(min_gov.get("minimalism_digest_lines") or [])
    invisible_digest = bool(min_gov.get("invisible_digest_mode"))
    closure_lines = list(closure_gov.get("closure_digest_lines") or [])
    closure_candidate = bool(closure_gov.get("operational_closure_candidate"))
    legacy_gov = gov.get("legacy") or ctx.get("flow_legacy") or {}
    legacy_lines = list(legacy_gov.get("legacy_digest_lines") or [])
    succession_ready = bool(legacy_gov.get("succession_readiness"))
    obs_gov = gov.get("observability") or ctx.get("flow_observability") or {}
    obs_lines = list(obs_gov.get("observability_digest_lines") or [])
    conv_gov = gov.get("convergence") or ctx.get("flow_convergence") or {}
    conv_lines = list(conv_gov.get("convergence_digest_lines") or [])

    lines = ["", "<b>Operational stewardship</b>"]
    if conv_gov.get("finalization_digest_quiet") and conv_lines:
        lines.append(f"• {html.escape(str(conv_lines[0])[:120])}")
        return lines
    if conv_gov.get("stewardship_recursion_detected") and conv_lines:
        lines.append(f"• {html.escape(str(conv_lines[0])[:120])}")
        return lines
    if obs_gov.get("canonical_observability_quiet") and obs_lines:
        lines.append(f"• {html.escape(str(obs_lines[0])[:120])}")
        return lines
    if obs_gov.get("observability_drift_detected") and obs_lines:
        lines.append(f"• {html.escape(str(obs_lines[0])[:120])}")
        return lines
    if succession_ready and legacy_lines:
        lines.append(f"• {html.escape(str(legacy_lines[0])[:120])}")
        return lines
    if closure_candidate and closure_lines:
        lines.append(f"• {html.escape(str(closure_lines[0])[:120])}")
        return lines
    idx = trust.get("operator_trust_index", "—")
    band = trust.get("operator_trust_band", "?")
    vit_gov = gov.get("vitality") or {}
    real = vit_gov.get("realism") or {}
    deg = gov.get("degradation") or dur.get("degradation") or {}
    starve = (ctx.get("publish_funnel") or {}).get("starvation") or {}
    all_calm = (
        str(deg.get("mode", "NORMAL")) == "NORMAL"
        and not starve.get("detected")
        and mat.get("operational_maturity_band") in ("STABLE", "MATURE")
        and (rehe.get("uptime_stability") or {}).get("uptime_stability_health") == "HEALTHY"
        and conf.get("operational_confidence_band") in ("TRUSTED", "CERTIFIED", None)
    )
    certified = conf.get("operational_confidence_band") == "CERTIFIED"

    if invisible_digest and minimalism_lines:
        for el in minimalism_lines[:2]:
            lines.append(f"• {html.escape(str(el)[:120])}")
    elif long_horizon and ultra_quiet and resilience_lines:
        for el in resilience_lines:
            lines.append(f"• {html.escape(str(el)[:120])}")
    elif institutional and ultra_quiet and doctrine_lines:
        for el in doctrine_lines:
            lines.append(f"• {html.escape(str(el)[:120])}")
    elif ultra_quiet and stewardship:
        lines.append(
            f"<code>{html.escape(str(horizon.get('stewardship_horizon_band', 'LONG')))}</code> · "
            f"~{horizon.get('stewardship_horizon_days', '—')}d horizon · exposure "
            f"{html.escape(str(exp.get('drift_exposure_band', 'MINIMAL')))}",
        )
    elif certified and stewardship and not ultra_quiet:
        lines.append(
            f"Confidence <code>{html.escape(str(conf.get('operational_confidence_band')))}</code> · "
            f"index {conf.get('operational_confidence_index')}",
        )
    elif not all_calm or not show_stewardship:
        lines.append(f"Trust {idx} · <code>{html.escape(str(band))}</code>")
        if real.get("operational_realism_index") is not None:
            lines.append(
                f"Realism {real.get('operational_realism_index')} · "
                f"<code>{html.escape(str(real.get('operational_realism_band', '?')))}</code>",
            )
        if deg.get("mode") and deg.get("mode") != "NORMAL":
            reasons = ", ".join(deg.get("reasons") or [])[:60]
            lines.append(f"Degradation <code>{html.escape(str(deg.get('mode')))}</code> {html.escape(reasons)}")
        elif conf.get("operational_confidence_index") is not None:
            lines.append(
                f"Confidence {conf.get('operational_confidence_index')} · "
                f"<code>{html.escape(str(conf.get('operational_confidence_band', '?')))}</code>",
            )
    elif mat.get("operational_maturity_index") is not None:
        lines.append(
            f"Maturity {mat.get('operational_maturity_index')} · "
            f"<code>{html.escape(str(mat.get('operational_maturity_band', '?')))}</code>",
        )

    mode = ctx.get("newsroom_mode")
    if not mode:
        mode = (ctx.get("flow_calibration") or {}).get("newsroom_mode")
    if isinstance(mode, dict):
        mode = mode.get("current_mode")
    if mode and mode != "STABLE":
        lines.append(f"Mode <code>{html.escape(str(mode))}</code>")

    if not (all_calm and certified) and not ultra_quiet and not institutional and not long_horizon and not invisible_digest:
        for b in cockpit.get("cockpit_bullets") or []:
            lines.append(f"• {html.escape(str(b))}")
        for w in cockpit.get("active_warnings") or []:
            tier = w.get("tier", "NOTICE")
            if tier not in ("WARNING", "CRITICAL") and (all_calm or ultra_quiet):
                continue
            prefix = "⚠" if tier in ("WARNING", "CRITICAL") else "·"
            lines.append(f"{prefix} [{tier}] {html.escape(str(w.get('message', ''))[:140])}")

    slim = gov.get("slimming") or ctx.get("flow_slimming") or {}
    change_band = (cert.get("change_pressure") or {}).get("change_pressure_band", "LOW")
    try:
        from bot.editorial.flow_health.slimming.telemetry_prune import should_show_slimming_panel

        if should_show_slimming_panel(ctx, slim) and change_band != "LOW" and not all_calm and not ultra_quiet:
            lines.append("")
            lines.append("<b>Maintainability</b>")
            cfg = slim.get("config_surface") or {}
            if cfg.get("config_complexity_band") not in (None, "low"):
                lines.append(
                    f"Config complexity {cfg.get('config_complexity_score')} "
                    f"({html.escape(str(cfg.get('config_complexity_band', '?')))})",
                )
            con = slim.get("consolidation") or {}
            if int(con.get("heuristic_density") or 0) >= 4:
                lines.append(f"Heuristic density {con.get('heuristic_density')}")
            sw = slim.get("state_weight") or {}
            if sw.get("adaptive_state_weight") is not None:
                lines.append(f"Adaptive state weight {sw.get('adaptive_state_weight')}")
            core = slim.get("core_health") or {}
            if core.get("operational_core_healthy") is False:
                lines.append("Core path stress — check starvation/degradation")
            cr = slim.get("change_risk") or {}
            safest = cr.get("safest_to_modify") or []
            if safest:
                lines.append(
                    "Low-risk to tune: " + html.escape(", ".join(safest[:3])),
                )
            prune = cockpit.get("telemetry_prune") or {}
            if int(prune.get("pruned_count") or 0) > 0:
                lines.append(f"Telemetry pruned {prune['pruned_count']} stable lines")
    except Exception:
        pass

    if not invisible_digest and not (institutional and ultra_quiet) and not (long_horizon and ultra_quiet):
        for el in stewardship:
            lines.append(f"• {html.escape(str(el)[:120])}")
    if resilience_lines and not (long_horizon and ultra_quiet) and not invisible_digest:
        for el in resilience_lines:
            if el not in stewardship:
                lines.append(f"• {html.escape(str(el)[:120])}")
    if doctrine_lines and not (institutional and ultra_quiet) and not (long_horizon and ultra_quiet) and not invisible_digest:
        for el in doctrine_lines:
            if el not in stewardship:
                lines.append(f"• {html.escape(str(el)[:120])}")
    if memory_lines and (not ultra_quiet or omem.get("recurrence_detected")) and not institutional and not long_horizon and not invisible_digest:
        for el in memory_lines:
            if el not in stewardship:
                lines.append(f"• {html.escape(str(el)[:120])}")
    if minimalism_lines and not invisible_digest and min_gov.get("entropy", {}).get("entropy_elevated"):
        for el in minimalism_lines:
            if el not in stewardship:
                lines.append(f"• {html.escape(str(el)[:120])}")
    if not ultra_quiet and not invisible_digest:
        for el in exec_lines:
            if el not in stewardship:
                lines.append(f"• {html.escape(str(el)[:120])}")

    if not stewardship and not all_calm and not ultra_quiet:
        prof = rehe.get("rehearsal_profile") or {}
        if prof.get("expected_behavior_summary"):
            lines.append(html.escape(str(prof["expected_behavior_summary"])[:140]))

    if not all_calm and not ultra_quiet:
        drift_narr = (rel.get("drift_narratives") or [])[:1]
        for narrative in drift_narr:
            if narrative not in stewardship:
                lines.append(f"• {html.escape(str(narrative)[:120])}")

    return lines
