from __future__ import annotations

from pathlib import Path
from typing import Any

from bot.editorial.flow_health.baseline_immunity import apply_baseline_immunity
from bot.editorial.flow_health.degradation import detect_degradation_mode
from bot.editorial.flow_health.hygiene import compute_adaptive_freshness, run_adaptive_hygiene
from bot.editorial.flow_health.influence import compute_active_influences
from bot.editorial.flow_health.low_observability import evaluate_low_observability_survival
from bot.editorial.flow_health.self_audit import build_self_audit_bullets, record_weekly_audit_snapshot
from bot.editorial.flow_health.simplicity import compute_operational_simplicity_index


def durability_governance_snapshot(
    *,
    db_path: Path | None = None,
    baseline: dict[str, Any],
    adaptive: dict[str, Any],
    calibration: dict[str, Any],
    trust_index: dict[str, Any],
    vitality: dict[str, Any],
    config_pressure: dict[str, Any],
    warning_pressure: float = 0.0,
    telemetry_ok: bool = True,
    current_vector: dict[str, float] | None = None,
) -> dict[str, Any]:
    hygiene = run_adaptive_hygiene()
    freshness = hygiene.get("adaptive_freshness") or compute_adaptive_freshness()

    low_obs = evaluate_low_observability_survival(
        warning_pressure=warning_pressure,
        trust_index=float(trust_index.get("operator_trust_index") or 0.75),
    )

    vitality_stale = bool(freshness.get("state_stale"))
    degradation = detect_degradation_mode(
        baseline=baseline,
        adaptive=adaptive,
        telemetry_ok=telemetry_ok,
        vitality_stale=vitality_stale,
    )

    immune_baseline = apply_baseline_immunity(baseline, current_vector=current_vector)
    influences = compute_active_influences(
        adaptive=adaptive,
        degradation=degradation,
        calibration={**calibration, "vitality": vitality, "rhythm": calibration.get("rhythm")},
    )

    simplicity = compute_operational_simplicity_index(
        config_pressure=config_pressure,
        warning_pressure=warning_pressure,
        influences=influences,
        degradation=degradation,
        baseline=immune_baseline,
        freshness=freshness,
    )

    vit_score = (vitality.get("vitality") or {}).get("editorial_vitality_score")
    real_score = (vitality.get("realism") or {}).get("operational_realism_index")

    record_weekly_audit_snapshot(
        trust_index=trust_index.get("operator_trust_index"),
        realism_index=real_score,
        vitality_score=vit_score,
        degradation_mode=str(degradation.get("mode")),
        simplicity_index=simplicity.get("operational_simplicity_index"),
        influence_count=int(influences.get("influence_count") or 0),
    )

    return {
        "degradation": degradation,
        "hygiene": hygiene,
        "freshness": freshness,
        "baseline_immunity": immune_baseline,
        "low_observability": low_obs,
        "influences": influences,
        "simplicity": simplicity,
        "self_audit_bullets": build_self_audit_bullets(),
    }
