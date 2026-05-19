from __future__ import annotations

from typing import Any

from bot.editorial.runtime_validation.degradation import verify_degradation_survivability
from bot.editorial.runtime_validation.digest import verify_digest_silence
from bot.editorial.runtime_validation.persistence import verify_persistence_aging
from bot.editorial.runtime_validation.restart import verify_restart_survivability
from bot.editorial.runtime_validation.scheduler import verify_scheduler_survivability
from bot.editorial.runtime_validation.telemetry import verify_telemetry_stability


def _operational_aging_summary(
    *,
    persistence: dict[str, Any],
    degradation: dict[str, Any],
    digest: dict[str, Any],
) -> dict[str, Any]:
    """Long-horizon calm — deterministic, not predictive."""
    calm = (
        persistence.get("bounded_persistence_ok")
        and degradation.get("operational_aging_ok")
        and not degradation.get("hidden_entropy_observed")
        and digest.get("digest_noise_drift", 1) < 0.35
    )
    fatigue = (
        persistence.get("continuity_storage_pressure", 0) > 0.9
        or degradation.get("hidden_entropy_observed")
    )
    return {
        "long_horizon_calm": calm,
        "operational_fatigue_detected": fatigue,
        "slow_drift_risk": persistence.get("persistence_growth_rate", 0) > 0.85,
    }


def build_runtime_validation_report(
    *,
    ctx: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
    loop_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Infrastructure validation snapshot — not a dashboard."""
    pulse = (ctx or {}).get("pulse") or {}

    persistence = verify_persistence_aging(metrics=metrics)
    digest = verify_digest_silence(ctx=ctx)
    scheduler = verify_scheduler_survivability(loop_snapshot=loop_snapshot, pulse=pulse)
    telemetry = verify_telemetry_stability(ctx=ctx)
    restart = verify_restart_survivability(metrics=metrics, loop_snapshot=loop_snapshot)
    degradation = verify_degradation_survivability(ctx=ctx, metrics=metrics)
    aging = _operational_aging_summary(
        persistence=persistence,
        degradation=degradation,
        digest=digest,
    )

    checks = {
        "persistence_bounded": persistence.get("bounded_persistence_ok"),
        "digest_silence_stable": digest.get("digest_silence_ok"),
        "scheduler_continuity": scheduler.get("scheduler_continuity_ok"),
        "telemetry_canonical": telemetry.get("canonical_telemetry_stability"),
        "restart_survivable": restart.get("restart_survivability_ok"),
        "no_hidden_entropy": not degradation.get("hidden_entropy_observed"),
        "long_horizon_calm": aging.get("long_horizon_calm"),
    }
    passed = sum(1 for v in checks.values() if v)
    overall_ok = passed >= len(checks) - 1

    return {
        "persistence": persistence,
        "digest": digest,
        "scheduler": scheduler,
        "telemetry": telemetry,
        "restart": restart,
        "degradation": degradation,
        "operational_aging": aging,
        "checks": checks,
        "checks_passed": passed,
        "checks_total": len(checks),
        "infrastructure_validation_ok": overall_ok,
        "summary_lines": render_validation_summary(
            persistence=persistence,
            digest=digest,
            scheduler=scheduler,
            telemetry=telemetry,
            restart=restart,
            degradation=degradation,
            aging=aging,
            overall_ok=overall_ok,
        ),
    }


def render_validation_summary(
    *,
    persistence: dict[str, Any],
    digest: dict[str, Any],
    scheduler: dict[str, Any],
    telemetry: dict[str, Any],
    restart: dict[str, Any],
    degradation: dict[str, Any],
    aging: dict[str, Any],
    overall_ok: bool,
) -> list[str]:
    """Calm operational validation lines — not an analytics report."""
    lines: list[str] = []
    if persistence.get("bounded_persistence_ok"):
        lines.append("Persistence remains bounded")
    else:
        lines.append("Persistence pressure detected — review metrics_json growth")

    if digest.get("digest_silence_ok"):
        lines.append("Digest silence stable")
    elif digest.get("quiet_modes", {}).get("invisible_digest"):
        lines.append("Digest noise drift under invisible mode")

    if scheduler.get("scheduler_continuity_ok"):
        lines.append("Scheduler continuity healthy")
    else:
        lines.append("Scheduler continuity needs attention")

    if telemetry.get("canonical_telemetry_stability"):
        lines.append("Telemetry propagation canonical")
    else:
        lines.append("Telemetry fragmentation or drift observed")

    if restart.get("restart_survivability_ok"):
        lines.append("Restart survivability confirmed")
    else:
        lines.append("Recovery path active or loop errors elevated")

    if not degradation.get("hidden_entropy_observed"):
        lines.append("No long-run entropy accumulation observed")
    else:
        lines.append("Operational entropy elevated — monitor calm runtime")

    if aging.get("long_horizon_calm") and overall_ok:
        lines.append("Long-horizon operational calm verified")

    return lines[:8]
