from __future__ import annotations

from typing import Any

from bot.editorial.flow_health.state import load_state


def analyze_drift_boundaries(
    *,
    baseline: dict[str, Any] | None = None,
    reliability: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Bounded slow drift across trust, realism, vitality, cadence."""
    st = load_state()
    audits = dict(st.get("weekly_audits") or {})
    breaches: list[str] = []

    if len(audits) >= 3:
        keys = sorted(audits.keys())[-4:]

        def _trend(key: str, limit: float) -> None:
            vals = [float((audits[k] or {}).get(key) or 0) for k in keys if (audits[k] or {}).get(key) is not None]
            if len(vals) >= 2 and vals[-1] - vals[0] < -limit:
                breaches.append(f"{key}_erosion")

        _trend("trust_index", 0.08)
        _trend("realism_index", 0.08)
        _trend("vitality_score", 0.1)
        _trend("simplicity_index", 0.12)

    base_dev = float((baseline or {}).get("baseline_deviation") or 0)
    if base_dev >= 0.22:
        breaches.append("baseline_drift")

    dens = (reliability or {}).get("telemetry_density") or {}
    if dens.get("telemetry_creep_detected"):
        breaches.append("telemetry_re_expansion")

    if baseline and baseline.get("immunity_active"):
        breaches.append("relaxation_normalization_risk")

    status = "WITHIN_BOUNDS"
    if len(breaches) >= 3:
        status = "BREACH"
    elif breaches:
        status = "ELEVATED"

    return {
        "drift_boundary_status": status,
        "drift_breaches": breaches,
        "baseline_deviation": round(base_dev, 3),
    }
