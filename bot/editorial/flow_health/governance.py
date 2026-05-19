from __future__ import annotations

from pathlib import Path
from typing import Any

from bot.editorial.flow_health.baseline_governance import (
    baseline_windows_summary,
    compute_baseline_deviation,
    update_daily_baseline,
    _vector_from_snapshot,
)
from bot.editorial.flow_health.config_pressure import analyze_configuration_pressure
from bot.editorial.flow_health.signal_compression import build_cockpit_summary
from bot.editorial.flow_health.surge_balance import detect_news_surge
from bot.editorial.flow_health.trust_index import compute_operator_trust_index
from bot.editorial.flow_health.durability import durability_governance_snapshot
from bot.editorial.flow_health.hygiene import compute_adaptive_freshness, run_adaptive_hygiene
from bot.editorial.flow_health.vitality_governance import vitality_governance_snapshot


def governance_snapshot(
    *,
    db_path: Path | None = None,
    cadence: dict[str, Any] | None = None,
    coverage: dict[str, Any] | None = None,
    calibration: dict[str, Any] | None = None,
    adaptive: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Long-window calibration governance bundle — lazy, fail-open."""
    path_str = str(db_path) if db_path else None
    hygiene_meta = run_adaptive_hygiene()
    freshness = hygiene_meta.get("adaptive_freshness") or compute_adaptive_freshness()
    telemetry_ok = True

    if cadence is None:
        from bot.editorial.flow_health.cadence import compute_cadence_health

        cadence = compute_cadence_health(db_path=db_path)
    if coverage is None:
        from bot.editorial.flow_health.coverage import compute_coverage_score

        coverage = compute_coverage_score(db_path=db_path)
    if calibration is None:
        from bot.editorial.flow_health.calibration import operational_calibration_snapshot

        calibration = operational_calibration_snapshot(db_path=db_path, adaptive=adaptive)
    if adaptive is None:
        from bot.editorial.flow_health.adaptive import adaptive_modulation

        adaptive = adaptive_modulation()

    vector = _vector_from_snapshot(
        cadence=cadence,
        coverage=coverage,
        calibration=calibration,
        adaptive=adaptive,
    )
    update_daily_baseline(vector)

    baseline = compute_baseline_deviation(vector)
    baseline["windows"] = baseline_windows_summary(vector)

    from bot.editorial.flow_health.degradation import detect_degradation_mode
    from bot.editorial.flow_health.reliability.operator_absence import (
        evaluate_operator_absence_resilience,
    )

    pre_degradation = detect_degradation_mode(
        baseline=baseline,
        adaptive=adaptive,
        telemetry_ok=telemetry_ok,
        vitality_stale=bool(freshness.get("state_stale")),
    )

    config_pressure = analyze_configuration_pressure()
    surge = detect_news_surge(db_path=path_str)

    warning_pressure = 0.0
    if baseline.get("drift_detected"):
        warning_pressure += 0.35
    if config_pressure.get("configuration_pressure_band") == "high":
        warning_pressure += 0.25
    elif config_pressure.get("configuration_pressure_band") == "moderate":
        warning_pressure += 0.12

    trust = compute_operator_trust_index(
        predictability=calibration.get("predictability") or {},
        baseline=baseline,
        config_pressure=config_pressure,
        warning_pressure=warning_pressure,
        digest_clarity=0.88,
        cadence=cadence,
        coverage=coverage,
    )

    operator_absence = evaluate_operator_absence_resilience(
        warning_pressure=warning_pressure,
        trust_index=float(trust.get("operator_trust_index") or 0.75),
    )

    vitality = vitality_governance_snapshot(
        db_path=db_path,
        cadence=cadence,
        coverage=coverage,
        trust_index=trust,
    )

    durability = durability_governance_snapshot(
        db_path=db_path,
        baseline=baseline,
        adaptive=adaptive,
        calibration=calibration,
        trust_index=trust,
        vitality=vitality,
        config_pressure=config_pressure,
        warning_pressure=warning_pressure,
        telemetry_ok=telemetry_ok,
        current_vector=vector,
    )
    baseline_out = durability.get("baseline_immunity") or baseline
    degradation = durability.get("degradation") or pre_degradation

    slimming: dict[str, Any] = {}
    try:
        from bot.editorial.flow_health.slimming import slimming_snapshot

        slimming = slimming_snapshot(
            adaptive=adaptive,
            influences=durability.get("influences"),
        )
    except Exception:
        pass

    reliability: dict[str, Any] = {}
    try:
        from bot.editorial.flow_health.reliability import reliability_snapshot

        reliability = reliability_snapshot(
            telemetry_ok=telemetry_ok,
            freshness=freshness,
            degradation=degradation,
            baseline=baseline_out,
            adaptive=adaptive,
            cadence=cadence,
            trust_index=trust,
            vitality=vitality,
            durability=durability,
            hygiene=hygiene_meta,
            config_pressure=config_pressure,
            warning_pressure=warning_pressure,
        )
    except Exception:
        pass

    rehearsal: dict[str, Any] = {}
    try:
        from bot.editorial.flow_health.rehearsal import rehearsal_snapshot

        gov_partial = {
            "baseline": baseline_out,
            "degradation": degradation,
            "durability": durability,
            "reliability": reliability,
            "slimming": slimming,
            "operator_absence": operator_absence,
        }
        rehearsal = rehearsal_snapshot(
            reliability=reliability,
            slimming=slimming,
            governance=gov_partial,
        )
    except Exception:
        pass

    certification: dict[str, Any] = {}
    try:
        from bot.editorial.flow_health.certification import certification_snapshot

        certification = certification_snapshot(
            governance=gov_partial,
            reliability=reliability,
            rehearsal=rehearsal,
            slimming=slimming,
        )
    except Exception:
        pass

    freeze_registry: dict[str, Any] = {}
    try:
        from bot.editorial.flow_health.freeze_registry import freeze_registry_snapshot

        freeze_registry = freeze_registry_snapshot(
            governance={**gov_partial, "certification": certification, "rehearsal": rehearsal},
            certification=certification,
            rehearsal=rehearsal,
            reliability=reliability,
        )
    except Exception:
        pass

    operational_memory: dict[str, Any] = {}
    try:
        from bot.editorial.flow_health.operational_memory import operational_memory_snapshot

        operational_memory = operational_memory_snapshot(
            governance={
                **gov_partial,
                "certification": certification,
                "rehearsal": rehearsal,
                "freeze_registry": freeze_registry,
            },
            certification=certification,
            rehearsal=rehearsal,
            freeze_registry=freeze_registry,
            reliability=reliability,
        )
    except Exception:
        pass

    doctrine: dict[str, Any] = {}
    try:
        from bot.editorial.flow_health.doctrine import doctrine_snapshot

        doctrine = doctrine_snapshot(
            governance={
                **gov_partial,
                "certification": certification,
                "rehearsal": rehearsal,
                "freeze_registry": freeze_registry,
                "operational_memory": operational_memory,
            },
            certification=certification,
            freeze_registry=freeze_registry,
            operational_memory=operational_memory,
            slimming=slimming,
            reliability=reliability,
        )
    except Exception:
        pass

    strategic_resilience: dict[str, Any] = {}
    try:
        from bot.editorial.flow_health.strategic_resilience import strategic_resilience_snapshot

        strategic_resilience = strategic_resilience_snapshot(
            governance={
                **gov_partial,
                "certification": certification,
                "rehearsal": rehearsal,
                "freeze_registry": freeze_registry,
                "operational_memory": operational_memory,
                "doctrine": doctrine,
            },
            certification=certification,
            freeze_registry=freeze_registry,
            operational_memory=operational_memory,
            doctrine=doctrine,
            reliability=reliability,
        )
    except Exception:
        pass

    minimalism: dict[str, Any] = {}
    try:
        from bot.editorial.flow_health.minimalism import minimalism_snapshot

        minimalism = minimalism_snapshot(
            governance={
                **gov_partial,
                "certification": certification,
                "rehearsal": rehearsal,
                "freeze_registry": freeze_registry,
                "operational_memory": operational_memory,
                "doctrine": doctrine,
                "strategic_resilience": strategic_resilience,
            },
        )
    except Exception:
        pass

    closure: dict[str, Any] = {}
    try:
        from bot.editorial.flow_health.closure import closure_snapshot

        closure = closure_snapshot(
            governance={
                **gov_partial,
                "certification": certification,
                "rehearsal": rehearsal,
                "freeze_registry": freeze_registry,
                "operational_memory": operational_memory,
                "doctrine": doctrine,
                "strategic_resilience": strategic_resilience,
                "minimalism": minimalism,
            },
        )
    except Exception:
        pass

    legacy: dict[str, Any] = {}
    try:
        from bot.editorial.flow_health.legacy import legacy_snapshot

        legacy = legacy_snapshot(
            governance={
                **gov_partial,
                "certification": certification,
                "rehearsal": rehearsal,
                "freeze_registry": freeze_registry,
                "operational_memory": operational_memory,
                "doctrine": doctrine,
                "strategic_resilience": strategic_resilience,
                "minimalism": minimalism,
                "closure": closure,
            },
        )
    except Exception:
        pass

    return {
        "baseline": baseline_out,
        "config_pressure": config_pressure,
        "surge": surge,
        "trust_index": trust,
        "vitality": vitality,
        "durability": durability,
        "degradation": degradation,
        "hygiene": hygiene_meta,
        "freshness": freshness,
        "slimming": slimming,
        "reliability": reliability,
        "operator_absence": operator_absence,
        "rehearsal": rehearsal,
        "certification": certification,
        "freeze_registry": freeze_registry,
        "operational_memory": operational_memory,
        "doctrine": doctrine,
        "strategic_resilience": strategic_resilience,
        "minimalism": minimalism,
        "closure": closure,
        "legacy": legacy,
    }


def enrich_governance_with_cockpit(ctx: dict[str, Any]) -> dict[str, Any]:
    """Full-context cockpit + trust refresh — call after collector assembles ctx."""
    gov = dict(ctx.get("flow_governance") or {})
    cockpit = build_cockpit_summary(ctx)
    gov["cockpit"] = cockpit
    trust = compute_operator_trust_index(
        predictability=(ctx.get("flow_calibration") or {}).get("predictability") or {},
        baseline=gov.get("baseline") or {},
        config_pressure=gov.get("config_pressure") or {},
        warning_pressure=float(cockpit.get("warning_pressure") or 0),
        digest_clarity=float(cockpit.get("digest_clarity") or 0.85),
        cadence=ctx.get("flow_cadence") or {},
        coverage=ctx.get("flow_coverage") or {},
    )
    gov["trust_index"] = trust
    try:
        vitality = vitality_governance_snapshot(
            cadence=ctx.get("flow_cadence"),
            coverage=ctx.get("flow_coverage"),
            trust_index=trust,
        )
        gov["vitality"] = vitality
    except Exception:
        pass
    try:
        from bot.editorial.flow_health.slimming import slimming_snapshot

        gov["slimming"] = slimming_snapshot(
            ctx=ctx,
            adaptive=ctx.get("flow_adaptive"),
            influences=(gov.get("durability") or {}).get("influences"),
        )
    except Exception:
        pass
    try:
        from bot.editorial.flow_health.reliability import reliability_snapshot

        gov["reliability"] = reliability_snapshot(
            ctx=ctx,
            telemetry_ok=True,
            freshness=gov.get("freshness"),
            degradation=gov.get("degradation"),
            baseline=gov.get("baseline"),
            adaptive=ctx.get("flow_adaptive"),
            cadence=ctx.get("flow_cadence"),
            trust_index=trust,
            vitality=gov.get("vitality"),
            durability=gov.get("durability"),
            hygiene=gov.get("hygiene"),
            config_pressure=gov.get("config_pressure"),
            cockpit=cockpit,
            warning_pressure=float(cockpit.get("warning_pressure") or 0),
        )
        dur = gov.get("durability") or {}
        if isinstance(dur, dict):
            dur = dict(dur)
            dur["self_audit_bullets"] = (gov["reliability"] or {}).get("drift_narratives") or []
            gov["durability"] = dur
    except Exception:
        pass
    try:
        from bot.editorial.flow_health.rehearsal import rehearsal_snapshot

        gov["rehearsal"] = rehearsal_snapshot(
            ctx=ctx,
            reliability=gov.get("reliability"),
            slimming=gov.get("slimming"),
            governance=gov,
            cockpit=cockpit,
        )
    except Exception:
        pass
    try:
        from bot.editorial.flow_health.certification import certification_snapshot

        gov["certification"] = certification_snapshot(
            ctx=ctx,
            governance=gov,
            reliability=gov.get("reliability"),
            rehearsal=gov.get("rehearsal"),
            slimming=gov.get("slimming"),
            cockpit=cockpit,
        )
    except Exception:
        pass
    try:
        from bot.editorial.flow_health.freeze_registry import freeze_registry_snapshot

        gov["freeze_registry"] = freeze_registry_snapshot(
            ctx=ctx,
            governance=gov,
            certification=gov.get("certification"),
            rehearsal=gov.get("rehearsal"),
            reliability=gov.get("reliability"),
            cockpit=cockpit,
        )
    except Exception:
        pass
    try:
        from bot.editorial.flow_health.operational_memory import operational_memory_snapshot

        gov["operational_memory"] = operational_memory_snapshot(
            ctx=ctx,
            governance=gov,
            certification=gov.get("certification"),
            rehearsal=gov.get("rehearsal"),
            freeze_registry=gov.get("freeze_registry"),
            reliability=gov.get("reliability"),
            cockpit=cockpit,
        )
    except Exception:
        pass
    try:
        from bot.editorial.flow_health.doctrine import doctrine_snapshot

        gov["doctrine"] = doctrine_snapshot(
            ctx=ctx,
            governance=gov,
            certification=gov.get("certification"),
            freeze_registry=gov.get("freeze_registry"),
            operational_memory=gov.get("operational_memory"),
            slimming=gov.get("slimming"),
            reliability=gov.get("reliability"),
            cockpit=cockpit,
        )
    except Exception:
        pass
    try:
        from bot.editorial.flow_health.strategic_resilience import strategic_resilience_snapshot

        vit = gov.get("vitality") or {}
        editorial_identity = {
            "editorial_vitality_score": (vit.get("vitality") or {}).get("editorial_vitality_score"),
            "operational_realism_index": (vit.get("realism") or {}).get("operational_realism_index"),
        }
        gov["strategic_resilience"] = strategic_resilience_snapshot(
            ctx=ctx,
            governance=gov,
            certification=gov.get("certification"),
            freeze_registry=gov.get("freeze_registry"),
            operational_memory=gov.get("operational_memory"),
            doctrine=gov.get("doctrine"),
            reliability=gov.get("reliability"),
            cockpit=cockpit,
            editorial_identity=editorial_identity,
        )
    except Exception:
        pass
    try:
        from bot.editorial.flow_health.minimalism import minimalism_snapshot

        gov["minimalism"] = minimalism_snapshot(ctx=ctx, governance=gov, cockpit=cockpit)
    except Exception:
        pass
    try:
        from bot.editorial.flow_health.closure import closure_snapshot

        gov["closure"] = closure_snapshot(ctx=ctx, governance=gov, cockpit=cockpit)
    except Exception:
        pass
    try:
        from bot.editorial.flow_health.legacy import legacy_snapshot

        gov["legacy"] = legacy_snapshot(ctx=ctx, governance=gov)
    except Exception:
        pass
    return gov
