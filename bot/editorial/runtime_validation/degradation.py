from __future__ import annotations

from typing import Any

from bot.editorial.flow_health.state import load_state


def verify_degradation_survivability(
    *,
    ctx: dict[str, Any] | None = None,
    metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Degraded-mode & operational aging heuristics — no prediction engine."""
    ctx = ctx or {}
    st = metrics if metrics is not None else load_state()
    gov = ctx.get("flow_governance") or {}

    deg = gov.get("degradation") or {}
    mode = str(deg.get("mode", "NORMAL"))
    degraded = mode not in ("NORMAL", "")

    obs_cont = st.get("observability_continuity") or {}
    conv_cont = st.get("convergence_continuity") or {}
    clos_cont = st.get("closure_continuity") or st.get("steady_state_continuity") or {}

    truth_streak = int(obs_cont.get("canonical_truth_streak_days") or 0)
    conv_streak = int(conv_cont.get("governance_convergence_streak_days") or 0)
    steady_streak = int(clos_cont.get("steady_state_streak_days") or 0)

    sediment_signals: list[str] = []
    if truth_streak >= 14 and conv_streak >= 14:
        sediment_signals.append("maturity_continuity_stable")
    if st.get("evolution_ledger") and len(st.get("evolution_ledger") or {}) > 20:
        sediment_signals.append("evolution_ledger_dense")

    min_g = gov.get("minimalism") or {}
    entropy = float(min_g.get("operational_entropy_accumulation") or 0)
    hidden_entropy = entropy >= 0.35 or bool(min_g.get("entropy", {}).get("entropy_elevated"))

    recovery_score = 0.75
    if not degraded:
        recovery_score += 0.15
    if truth_streak >= 7:
        recovery_score += 0.05
    if hidden_entropy:
        recovery_score -= 0.2

    aging_ok = not hidden_entropy and truth_streak >= 0

    return {
        "degraded_runtime_recovery": round(max(0.0, min(1.0, recovery_score)), 3),
        "degradation_mode": mode,
        "currently_degraded": degraded,
        "operational_aging_ok": aging_ok,
        "hidden_entropy_observed": hidden_entropy,
        "governance_sediment_signals": sediment_signals[:6],
        "continuity_streaks": {
            "canonical_truth_days": truth_streak,
            "convergence_days": conv_streak,
            "steady_state_days": steady_streak,
        },
    }
