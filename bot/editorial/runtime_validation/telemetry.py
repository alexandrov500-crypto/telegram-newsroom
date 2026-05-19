from __future__ import annotations

from typing import Any

_FLOW_TELEMETRY_PREFIXES = ("flow_", "operational_", "governance_", "stewardship_", "canonical_")


def verify_telemetry_stability(
    *,
    ctx: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Collector growth & canonical propagation — no telemetry platform."""
    ctx = ctx or {}
    issues: list[str] = []

    flow_keys = [k for k in ctx if k.startswith(_FLOW_TELEMETRY_PREFIXES)]
    null_flow = sum(1 for k in flow_keys if ctx.get(k) is None)
    if null_flow >= 5:
        issues.append("stale_top_level_telemetry_nulls")

    gov = ctx.get("flow_governance") or {}
    obs = gov.get("observability") or ctx.get("flow_observability") or {}
    prop = obs.get("propagation") or {}
    collector_ok = prop.get("propagation_coherent", True)
    if not collector_ok:
        issues.extend((prop.get("propagation_signals") or [])[:3])

    fragmentation = len(issues) >= 2 or null_flow >= 8
    key_count = len(ctx)
    growth_rate = round(min(1.0, key_count / 220), 3)

    drift_digest = False
    if obs.get("observability_drift_detected"):
        drift_digest = True
        issues.append("observability_drift_active")

    canonical_stable = (
        collector_ok
        and not fragmentation
        and obs.get("governance_cohesion_status") in ("COHERENT", "CANONICAL", None)
    )

    return {
        "telemetry_growth_rate": growth_rate,
        "collector_integrity_ok": collector_ok,
        "telemetry_fragmentation_detected": fragmentation,
        "canonical_telemetry_stability": canonical_stable,
        "telemetry_key_count": key_count,
        "flow_telemetry_null_count": null_flow,
        "telemetry_issues": issues[:8],
    }
