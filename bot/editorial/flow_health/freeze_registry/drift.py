from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bot.editorial.flow_health.state import load_state, save_state

_ALL_SUBSYSTEMS = (
    "publish_guard",
    "cadence_tuning",
    "relaxation_governance",
    "clustering_heuristics",
    "digest_wording",
    "certification",
    "rehearsal",
    "slimming",
    "degradation_modes",
    "trust_calibration",
)


def _utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _trend(change_count: int) -> str:
    if change_count >= 5:
        return "VOLATILE"
    if change_count >= 2:
        return "ACTIVE"
    return "CALM"


def _infer_churn_subsystems(
    *,
    governance: dict[str, Any] | None = None,
    certification: dict[str, Any] | None = None,
    ctx: dict[str, Any] | None = None,
) -> set[str]:
    gov = governance or {}
    cert = certification or {}
    ctx = ctx or {}
    churn: set[str] = set()

    stab = cert.get("stabilization_freeze") or {}
    for _ in stab.get("freeze_violations") or []:
        churn.add("cadence_tuning")
        churn.add("relaxation_governance")

    if str((gov.get("degradation") or {}).get("mode", "NORMAL")) != "NORMAL":
        churn.add("degradation_modes")

    chg = cert.get("change_pressure") or {}
    if chg.get("change_pressure_band") in ("ELEVATED", "DESTABILIZING"):
        churn.update({"cadence_tuning", "relaxation_governance", "trust_calibration"})

    flow = ctx.get("publish_funnel") or {}
    if (flow.get("starvation") or {}).get("detected"):
        churn.add("publish_guard")

    rehe = gov.get("rehearsal") or {}
    if (rehe.get("drift_boundaries") or {}).get("drift_boundary_status") != "WITHIN_BOUNDS":
        churn.add("rehearsal")

    return churn


def touch_evolution_ledger(
    *,
    governance: dict[str, Any] | None = None,
    certification: dict[str, Any] | None = None,
    ctx: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Rolling 30d operational churn metadata — no diffs, no commits."""
    churn = _infer_churn_subsystems(governance=governance, certification=certification, ctx=ctx)
    try:
        st = load_state()
        ledger: dict[str, dict[str, Any]] = dict(st.get("evolution_ledger") or {})
        touch_meta = dict(st.get("evolution_ledger_touch") or {})
        today = _utc_day()

        prior_churn = set(touch_meta.get("churn") or [])
        if touch_meta.get("day") != today:
            for name in _ALL_SUBSYSTEMS:
                entry = dict(ledger.get(name) or {})
                if name not in churn:
                    entry["last_modified_days"] = min(999, int(entry.get("last_modified_days") or 0) + 1)
                cnt = int(entry.get("change_count_30d") or 0)
                if touch_meta.get("day") and name not in churn:
                    cnt = max(0, cnt - 1)
                entry["change_count_30d"] = cnt
                entry["stability_trend"] = _trend(cnt)
                ledger[name] = entry
            touch_meta = {"day": today, "churn": []}
            prior_churn = set()

        new_churn = churn - prior_churn
        for name in new_churn:
            entry = dict(ledger.get(name) or {})
            entry["change_count_30d"] = min(30, int(entry.get("change_count_30d") or 0) + 1)
            entry["last_modified_days"] = 0
            entry["stability_trend"] = _trend(int(entry["change_count_30d"]))
            ledger[name] = entry

        touch_meta["churn"] = sorted(churn | prior_churn)
        save_state(metrics={"evolution_ledger": ledger, "evolution_ledger_touch": touch_meta})
        return ledger
    except Exception:
        return {}


def evolution_volatility_score(ledger: dict[str, dict[str, Any]]) -> float:
    if not ledger:
        return 0.0
    volatile = sum(1 for e in ledger.values() if e.get("stability_trend") == "VOLATILE")
    active = sum(1 for e in ledger.values() if e.get("stability_trend") == "ACTIVE")
    return round(min(1.0, volatile * 0.25 + active * 0.08), 3)
