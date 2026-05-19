from __future__ import annotations

import json
import os
from typing import Any

from bot.editorial.flow_health.state import load_state, save_state


def minimize_adaptive_state() -> dict[str, Any]:
    """
    Lazy state minimization — compresses history, drops obsolete keys.
    Called from hygiene path; no background loop.
    """
    if os.getenv("ADAPTIVE_STATE_MINIMIZE", "true").strip().lower() not in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return {"minimized": False}

    st = load_state()
    before_len = len(json.dumps({k: v for k, v in st.items() if k != "recovery_activated_at"}))

    audits = dict(st.get("weekly_audits") or {})
    keys = sorted(audits.keys())[-4:]
    audits = {k: audits[k] for k in keys}

    deg_hist = list(st.get("degradation_mode_history") or [])[-12:]

    metrics_patch: dict[str, Any] = {
        "weekly_audits": audits,
        "degradation_mode_history": deg_hist,
    }
    for obsolete in ("last_effective_scale", "baseline_updated_at"):
        if obsolete in st and obsolete not in metrics_patch:
            metrics_patch[obsolete] = st.get(obsolete)

    save_state(metrics=metrics_patch)

    after_st = load_state()
    after_len = len(json.dumps({k: v for k, v in after_st.items() if k != "recovery_activated_at"}))
    weight = round(min(1.0, after_len / 12000.0), 3)

    return {
        "minimized": True,
        "adaptive_state_weight": weight,
        "state_bytes_estimate": after_len,
        "bytes_reduced": max(0, before_len - after_len),
    }
