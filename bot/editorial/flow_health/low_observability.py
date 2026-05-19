from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from bot.editorial.flow_health.hygiene import _parse_iso
from bot.editorial.flow_health.state import load_state, save_state


def touch_operator_digest_seen() -> None:
    try:
        save_state(
            metrics={
                "last_operator_digest_at": datetime.now(timezone.utc).isoformat(),
                "low_observability_active": False,
            },
        )
    except Exception:
        pass


def evaluate_low_observability_survival(
    *,
    warning_pressure: float = 0.0,
    trust_index: float | None = None,
) -> dict[str, Any]:
    """
    When digest unseen for days and stress signals rise, bias toward conservative modulation.
    """
    if os.getenv("LOW_OBSERVABILITY_SURVIVAL_ENABLED", "true").strip().lower() not in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return {"low_observability_active": False}

    st = load_state()
    last = _parse_iso(str(st.get("last_operator_digest_at", "")))
    hours_unseen = 999.0
    if last:
        hours_unseen = (datetime.now(timezone.utc) - last).total_seconds() / 3600.0

    try:
        unseen_threshold = float(os.getenv("LOW_OBS_HOURS_UNSEEN", "72"))
    except ValueError:
        unseen_threshold = 72.0

    active = hours_unseen >= unseen_threshold and (
        warning_pressure >= 0.35 or (trust_index is not None and trust_index < 0.68)
    )

    if active:
        try:
            save_state(metrics={"low_observability_active": True})
        except Exception:
            pass

    return {
        "low_observability_active": active,
        "hours_since_digest": round(hours_unseen, 1),
        "conservative_bias": active,
    }
