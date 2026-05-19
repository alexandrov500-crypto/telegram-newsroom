from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any


def effective_canary_max_per_hour(*, cadence_health: float | None = None) -> dict[str, Any]:
    """
    Cadence-aware canary cap — never removes safety ceiling.
    Low cadence health → modest cap increase for pilot visibility.
    """
    try:
        base = int(os.getenv("LIVE_CANARY_MAX_PER_HOUR", "3"))
    except ValueError:
        base = 3
    try:
        ceiling = int(os.getenv("CANARY_CAP_CEILING", "6"))
    except ValueError:
        ceiling = 6

    if cadence_health is None:
        try:
            from bot.editorial.flow_health.cadence import compute_cadence_health

            cadence_health = float(compute_cadence_health().get("cadence_health") or 1.0)
        except Exception:
            cadence_health = 1.0

    effective = base
    boost = 0
    if cadence_health < 0.45:
        boost += 1
    if cadence_health < 0.30:
        boost += 1

    hour = datetime.now(timezone.utc).hour
    overnight = hour < 6 or hour >= 22
    if overnight and os.getenv("CANARY_OVERNIGHT_RELAX", "true").lower() in ("1", "true", "yes", "on"):
        boost += 1

    effective = min(ceiling, base + boost)

    approval_relaxed = False
    if cadence_health < 0.40 and os.getenv("CANARY_CADENCE_APPROVAL_RELAX", "false").lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        approval_relaxed = True

    return {
        "base_cap": base,
        "effective_cap": effective,
        "ceiling": ceiling,
        "cadence_health": round(cadence_health, 3),
        "overnight_boost": overnight,
        "approval_relax_advisory": approval_relaxed,
    }


def cadence_aware_requires_approval(
    *,
    default_requires: bool,
    operator_approved: bool,
    publish_confidence: float,
) -> bool:
    """
    When cadence very low, high-confidence items may skip mandatory approval (canary only).
    Default off via CANARY_CADENCE_APPROVAL_RELAX=false.
    """
    if operator_approved or not default_requires:
        return default_requires
    bal = effective_canary_max_per_hour()
    if not bal.get("approval_relax_advisory"):
        return True
    if publish_confidence >= 0.78:
        return False
    return True
