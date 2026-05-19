from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from bot.editorial.flow_health.hygiene import _parse_iso
from bot.editorial.flow_health.low_observability import evaluate_low_observability_survival
from bot.editorial.flow_health.state import load_state, save_state


def evaluate_operator_absence_resilience(
    *,
    warning_pressure: float = 0.0,
    trust_index: float | None = None,
) -> dict[str, Any]:
    """
    Extended absence handling — conservative bias without autonomous reconfiguration.
    """
    base = evaluate_low_observability_survival(
        warning_pressure=warning_pressure,
        trust_index=trust_index,
    )
    st = load_state()
    last = _parse_iso(str(st.get("last_operator_digest_at", "")))
    hours = float(base.get("hours_since_digest") or 999.0)

    try:
        mild_h = float(os.getenv("OPERATOR_ABSENCE_MILD_HOURS", "48"))
        severe_h = float(os.getenv("LOW_OBS_HOURS_UNSEEN", "72"))
    except ValueError:
        mild_h, severe_h = 48.0, 72.0

    level = "PRESENT"
    if hours >= severe_h:
        level = "EXTENDED_ABSENCE"
    elif hours >= mild_h:
        level = "MILD_ABSENCE"

    conservative = level != "PRESENT"
    digest_simplify = level == "EXTENDED_ABSENCE"
    reduce_aggression = conservative

    if conservative:
        try:
            save_state(
                metrics={
                    "operator_absence_level": level,
                    "low_observability_active": level == "EXTENDED_ABSENCE",
                },
            )
        except Exception:
            pass

    return {
        **base,
        "operator_absence_level": level,
        "conservative_operation": conservative,
        "digest_simplification": digest_simplify,
        "reduce_adaptive_aggression": reduce_aggression,
        "unattended_safe_mode": level == "EXTENDED_ABSENCE" and warning_pressure < 0.5,
    }
