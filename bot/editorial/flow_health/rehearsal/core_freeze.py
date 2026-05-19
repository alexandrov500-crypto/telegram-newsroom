from __future__ import annotations

from typing import Any

from bot.editorial.flow_health.state import load_state


def validate_core_freeze_candidate(
    *,
    ctx: dict[str, Any] | None = None,
    reliability: dict[str, Any] | None = None,
    maintenance: dict[str, Any] | None = None,
    uptime: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Whether operational core is stable enough to enter long-duration freeze."""
    ctx = ctx or {}
    flow = ctx.get("publish_funnel") or {}
    starve = bool((flow.get("starvation") or {}).get("detected"))
    rate = ctx.get("publish_success_rate")
    low_rate = rate is not None and float(rate) < 0.5

    rel = reliability or {}
    freeze_status = (rel.get("freeze_discipline") or {}).get("freeze_discipline_status", "")
    churn = freeze_status == "HIGH_TUNING_CHURN"
    maint = (maintenance or {}).get("maintenance_readiness", "CAUTION")
    up = (uptime or {}).get("uptime_stability_health", "WATCH")

    st = load_state()
    audits = st.get("weekly_audits") or {}
    mode_stable = True
    if len(audits) >= 2:
        modes = [str((audits[k] or {}).get("degradation_mode", "NORMAL")) for k in sorted(audits.keys())[-3:]]
        mode_stable = modes.count("NORMAL") >= len(modes) - 1

    candidate = (
        not starve
        and not low_rate
        and not churn
        and maint == "READY"
        and up == "HEALTHY"
        and mode_stable
    )

    return {
        "core_freeze_candidate": candidate,
        "blockers": [
            b
            for b, cond in (
                ("starvation_active", starve),
                ("publish_success_low", low_rate),
                ("config_churn", churn),
                ("maintenance_not_ready", maint != "READY"),
                ("uptime_unstable", up != "HEALTHY"),
                ("degradation_modes_unstable", not mode_stable),
            )
            if cond
        ],
    }
