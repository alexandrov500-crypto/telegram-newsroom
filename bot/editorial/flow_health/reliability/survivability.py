from __future__ import annotations

from typing import Any

from bot.editorial.flow_health.state import load_state


def validate_survivability(
    *,
    telemetry_ok: bool = True,
    freshness: dict[str, Any] | None = None,
    degradation: dict[str, Any] | None = None,
    baseline: dict[str, Any] | None = None,
    low_obs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Heuristic self-checks (no fault injection) — validates graceful degradation paths exist.
    """
    checks: list[dict[str, str]] = []
    passed = 0
    freshness = freshness or {}
    degradation = degradation or {}
    baseline = baseline or {}
    low_obs = low_obs or {}

    def _check(name: str, ok: bool, detail: str) -> None:
        nonlocal passed
        checks.append({"check": name, "ok": "pass" if ok else "warn", "detail": detail})
        if ok:
            passed += 1

    _check(
        "telemetry_loss_path",
        not telemetry_ok or str(degradation.get("mode")) in ("TELEMETRY_DEGRADED", "SIMPLIFIED", "NORMAL"),
        f"mode={degradation.get('mode')}",
    )
    _check(
        "stale_baseline_path",
        not freshness.get("state_stale") or str(degradation.get("mode")) != "NORMAL",
        "stale state triggers simplified path",
    )
    _check(
        "baseline_drift_handled",
        not baseline.get("drift_detected") or float(baseline.get("baseline_deviation") or 0) < 0.5,
        f"deviation={baseline.get('baseline_deviation')}",
    )
    st = load_state()
    _check("trend_history_present", bool(st.get("baseline_daily")), "daily baseline rolls exist")
    _check(
        "operator_absence_path",
        bool(low_obs.get("hours_since_digest") is not None),
        "digest tracking active",
    )
    _check(
        "fail_open_default",
        bool(degradation.get("gates") or degradation.get("mode")),
        "degradation gates available",
    )

    total = len(checks)
    score = round(passed / max(1, total), 3)
    band = "STRONG" if score >= 0.85 else "ADEQUATE" if score >= 0.65 else "FRAGILE"

    return {
        "survivability_score": score,
        "survivability_band": band,
        "checks": checks,
        "checks_passed": passed,
        "checks_total": total,
    }
