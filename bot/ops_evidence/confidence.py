from __future__ import annotations

from typing import Any

from bot.ops_evidence.types import ConfidenceBand


def compute_operational_confidence(
    *,
    runtime: dict[str, Any],
    publish_stats: dict[str, Any],
    trust_snapshot: dict[str, Any],
    agreement: dict[str, Any],
    incident_count: int,
    timeline_direction: str,
) -> dict[str, Any]:
    """Newsroom-level operational confidence index (advisory)."""
    components: dict[str, float] = {}

    pulse = runtime.get("pulse") or {}
    lag = float(pulse.get("event_loop_lag_max") or 0)
    stalled = int(pulse.get("stalled_loop_events") or 0)
    runtime_score = 1.0
    if lag > 0.8:
        runtime_score -= 0.35
    elif lag > 0.4:
        runtime_score -= 0.15
    if stalled > 0:
        runtime_score -= min(0.4, stalled * 0.08)
    if runtime.get("stability", {}).get("recovery_storms"):
        runtime_score -= 0.2
    components["runtime_stability"] = max(0.0, min(1.0, runtime_score))

    success = publish_stats.get("success_rate")
    if success is not None:
        components["publish_reliability"] = float(success)
    else:
        avg = runtime.get("publish_success_rate_avg")
        components["publish_reliability"] = float(avg) if avg is not None else 0.7

    subs = trust_snapshot.get("subsystems") or {}
    if subs:
        rels = [float(m.get("reliability") or 0.5) for m in subs.values()]
        components["subsystem_trust"] = sum(rels) / len(rels)
    else:
        components["subsystem_trust"] = 0.55

    totals = agreement.get("totals") or {}
    rated = int(totals.get("rated") or 0)
    if rated >= 2:
        good = int(totals.get("good") or 0)
        components["operator_agreement"] = good / rated
    else:
        components["operator_agreement"] = 0.65

    components["incident_penalty"] = max(0.0, 1.0 - min(0.5, incident_count * 0.05))

    if timeline_direction == "improving":
        components["evolution_bonus"] = 0.08
    elif timeline_direction == "degrading":
        components["evolution_bonus"] = -0.1
    else:
        components["evolution_bonus"] = 0.0

    weights = {
        "runtime_stability": 0.25,
        "publish_reliability": 0.2,
        "subsystem_trust": 0.25,
        "operator_agreement": 0.15,
        "incident_penalty": 0.15,
    }
    score = sum(components.get(k, 0.5) * w for k, w in weights.items())
    score += components.get("evolution_bonus", 0.0)
    score = max(0.0, min(1.0, score))

    band = _band_for_score(score)
    return {
        "score": round(score, 3),
        "band": band.value,
        "components": {k: round(v, 3) for k, v in components.items()},
    }


def _band_for_score(score: float) -> ConfidenceBand:
    if score >= 0.82:
        return ConfidenceBand.HIGH_CONFIDENCE
    if score >= 0.68:
        return ConfidenceBand.STABLE
    if score >= 0.5:
        return ConfidenceBand.STABILIZING
    return ConfidenceBand.FRAGILE
