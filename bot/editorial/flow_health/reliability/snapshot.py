from __future__ import annotations

from typing import Any

from bot.editorial.flow_health.reliability.drift_narrative import build_operational_drift_narratives
from bot.editorial.flow_health.reliability.freeze_discipline import analyze_freeze_discipline
from bot.editorial.flow_health.reliability.maturity import compute_operational_maturity_index
from bot.editorial.flow_health.reliability.operator_absence import evaluate_operator_absence_resilience
from bot.editorial.flow_health.reliability.recovery_envelope import validate_recovery_envelope
from bot.editorial.flow_health.reliability.runtime_fatigue import compute_runtime_fatigue
from bot.editorial.flow_health.reliability.survivability import validate_survivability
from bot.editorial.flow_health.reliability.telemetry_density import measure_telemetry_density


def reliability_snapshot(
    *,
    ctx: dict[str, Any] | None = None,
    telemetry_ok: bool = True,
    freshness: dict[str, Any] | None = None,
    degradation: dict[str, Any] | None = None,
    baseline: dict[str, Any] | None = None,
    adaptive: dict[str, Any] | None = None,
    cadence: dict[str, Any] | None = None,
    trust_index: dict[str, Any] | None = None,
    vitality: dict[str, Any] | None = None,
    durability: dict[str, Any] | None = None,
    hygiene: dict[str, Any] | None = None,
    config_pressure: dict[str, Any] | None = None,
    cockpit: dict[str, Any] | None = None,
    warning_pressure: float = 0.0,
) -> dict[str, Any]:
    """Long-run reliability validation bundle — advisory only."""
    absence = evaluate_operator_absence_resilience(
        warning_pressure=warning_pressure,
        trust_index=float((trust_index or {}).get("operator_trust_index") or 0.75),
    )
    survivability = validate_survivability(
        telemetry_ok=telemetry_ok,
        freshness=freshness,
        degradation=degradation,
        baseline=baseline,
        low_obs=absence,
    )
    fatigue = compute_runtime_fatigue(
        degradation=degradation,
        hygiene=hygiene,
        durability=durability,
    )
    density = measure_telemetry_density(cockpit=cockpit, ctx=ctx)
    envelope = validate_recovery_envelope(
        adaptive=adaptive,
        cadence=cadence,
        degradation=degradation,
    )
    freeze = analyze_freeze_discipline(config_pressure=config_pressure)
    realism = (vitality or {}).get("realism") or {}
    simplicity = (durability or {}).get("simplicity") or {}
    maturity = compute_operational_maturity_index(
        trust_index=trust_index,
        realism=realism,
        simplicity=simplicity,
        survivability=survivability,
        fatigue=fatigue,
        telemetry_density=density,
        recovery_envelope=envelope,
        degradation=degradation,
    )
    narratives = build_operational_drift_narratives()

    return {
        "freeze_discipline": freeze,
        "survivability": survivability,
        "runtime_fatigue": fatigue,
        "telemetry_density": density,
        "recovery_envelope": envelope,
        "operator_absence": absence,
        "operational_maturity": maturity,
        "drift_narratives": narratives,
    }
