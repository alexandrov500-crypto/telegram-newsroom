from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bot.editorial.flow_health.state import load_state
from bot.editorial.runtime_validation.baseline import load_baseline_history


def identify_dead_complexity_signals(
    *,
    ctx: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Advisory hints for manual review — no auto-removal."""
    ctx = ctx or {}
    st = metrics if metrics is not None else load_state()
    hints: list[str] = []

    null_flow = sum(
        1
        for k, v in ctx.items()
        if k.startswith("flow_") and v is None
    )
    if null_flow >= 3:
        hints.append("unused_top_level_flow_telemetry_nulls")

    gov = ctx.get("flow_governance") or {}
    for layer in ("observability", "convergence"):
        block = gov.get(layer) or {}
        if not block.get("observability_digest_lines") and not block.get("convergence_digest_lines"):
            if layer == "observability" and block.get("canonical_observability_quiet"):
                hints.append("observability_digest_permanently_silent")
            if layer == "convergence" and block.get("finalization_digest_quiet"):
                hints.append("convergence_digest_permanently_silent")

    for key in (
        "evidence_daily",
        "evolution_ledger",
        "operational_memory",
        "legacy_memory",
    ):
        val = st.get(key)
        if isinstance(val, dict) and len(val) == 0:
            hints.append(f"empty_continuity_or_memory_key_{key}")

    omem = st.get("operational_memory") or {}
    if isinstance(omem, dict) and not omem.get("incidents") and omem.get("touch"):
        hints.append("operational_memory_touch_without_incidents")

    if gov.get("convergence", {}).get("governance_finalization_candidate") and gov.get(
        "minimalism", {},
    ).get("invisible_digest_mode"):
        hints.append("finalization_quiet_with_full_governance_stack_present")

    return {
        "dead_complexity_hints": hints[:12],
        "manual_review_recommended": len(hints) >= 2,
    }


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def build_monthly_stability_review(
    *,
    weekly_history: list[dict[str, Any]] | None = None,
    current_report: dict[str, Any] | None = None,
    dead_complexity: dict[str, Any] | None = None,
    month_id: str | None = None,
) -> dict[str, Any]:
    """Monthly preservation review — not a subsystem, not a dashboard."""
    now = datetime.now(timezone.utc)
    month_id = month_id or now.strftime("%Y-%m")
    history = weekly_history if weekly_history is not None else load_baseline_history(limit=5)
    report = current_report or {}
    dead = dead_complexity or {}

    recent = history[-4:] if len(history) >= 4 else history
    growth_rates = [
        float((r.get("persistence") or {}).get("persistence_growth_rate") or 0)
        for r in recent
    ]
    digest_lines = [
        float((r.get("digest") or {}).get("digest_line_count") or 0) for r in recent
    ]
    validation_ok = [
        bool(r.get("infrastructure_validation_ok")) for r in recent
    ]
    hidden_entropy = [
        bool((r.get("calmness") or {}).get("hidden_entropy_observed")) for r in recent
    ]

    avg_growth = _avg(growth_rates)
    avg_digest = _avg(digest_lines)
    validation_stable = len(validation_ok) >= 2 and all(validation_ok[-2:])
    entropy_hits = sum(hidden_entropy)

    issues: list[str] = []
    if avg_growth is not None and avg_growth > 0.75:
        issues.append("persistence_growth_elevated")
    if avg_digest is not None and avg_digest > 6:
        issues.append("digest_verbosity_creep")
    if entropy_hits >= 2:
        issues.append("repeated_hidden_entropy")
    if not validation_stable and recent:
        issues.append("validation_intermittent")
    if dead.get("manual_review_recommended"):
        issues.append("dead_complexity_hints_present")

    cur_p = (report.get("persistence") or {})
    if not cur_p.get("bounded_persistence_ok", True):
        issues.append("current_boundedness_violation")
    if report.get("telemetry", {}).get("telemetry_fragmentation_detected"):
        issues.append("telemetry_fragmentation")
    if report.get("scheduler", {}).get("stalled_loops"):
        issues.append("scheduler_stalls")

    if len(issues) >= 2 or "current_boundedness_violation" in issues:
        verdict = "surgical_maintenance_required"
    elif issues:
        verdict = "observe"
    else:
        verdict = "stable"

    return {
        "month_id": month_id,
        "recorded_at": now.isoformat(),
        "weeks_reviewed": len(recent),
        "weekly_baseline_drift": {
            "avg_persistence_growth_rate": round(avg_growth, 3) if avg_growth is not None else None,
            "avg_digest_line_count": round(avg_digest, 2) if avg_digest is not None else None,
            "validation_stable": validation_stable,
            "hidden_entropy_weeks": entropy_hits,
        },
        "current_validation_ok": report.get("infrastructure_validation_ok"),
        "review_issues": issues,
        "monthly_verdict": verdict,
        "dead_complexity": dead,
        "preservation_kpis": {
            "digest_quiet": avg_digest is not None and avg_digest <= 4,
            "persistence_near_flat": avg_growth is not None and avg_growth < 0.5,
            "telemetry_canonical": (report.get("telemetry") or {}).get(
                "canonical_telemetry_stability",
            ),
            "long_horizon_calm": (report.get("operational_aging") or {}).get("long_horizon_calm"),
        },
        "summary_lines": _monthly_summary_lines(verdict=verdict, issues=issues, kpis={
            "digest_quiet": avg_digest is not None and avg_digest <= 4,
            "persistence_near_flat": avg_growth is not None and avg_growth < 0.5,
        }),
    }


def _monthly_summary_lines(
    *,
    verdict: str,
    issues: list[str],
    kpis: dict[str, bool],
) -> list[str]:
    lines: list[str] = []
    if verdict == "stable":
        lines.append("Monthly review: infrastructure remains preservation-stable")
    elif verdict == "observe":
        lines.append("Monthly review: observe — minor drift signals without urgent action")
    else:
        lines.append("Monthly review: surgical maintenance required — evidence-backed fixes only")

    if kpis.get("digest_quiet"):
        lines.append("Digest silence preserved across recent weeks")
    if kpis.get("persistence_near_flat"):
        lines.append("Persistence growth remains near-flat")
    if issues:
        lines.append(f"Signals: {', '.join(issues[:4])}")
    return lines[:6]
