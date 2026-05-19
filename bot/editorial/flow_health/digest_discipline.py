from __future__ import annotations

import os
from typing import Any

from bot.editorial.flow_health.funnel import _load_window
from bot.editorial.flow_health.state import load_state, save_state


def _max_digest_ratio() -> float:
    try:
        return float(os.getenv("DIGEST_MAX_RATIO_24H", "0.35"))
    except ValueError:
        return 0.35


def _max_consecutive() -> int:
    try:
        return int(os.getenv("DIGEST_MAX_CONSECUTIVE", "2"))
    except ValueError:
        return 2


def compute_digest_dependency(*, hours: int = 24) -> dict[str, Any]:
    totals, rejects = _load_window(hours)
    published = int(totals.get("PUBLISHED", 0))
    digest_publishes = int(rejects.get("recovery_digest", 0))
    ratio = round(digest_publishes / max(1, published), 3) if published else 0.0

    st = load_state()
    consecutive = int(st.get("consecutive_digest_recoveries") or 0)
    digest_heavy = ratio >= _max_digest_ratio() or consecutive >= _max_consecutive()

    return {
        "digest_publishes": digest_publishes,
        "normal_publishes_estimate": max(0, published - digest_publishes),
        "digest_to_publish_ratio": ratio,
        "consecutive_digest_recoveries": consecutive,
        "digest_heavy": digest_heavy,
        "max_ratio": _max_digest_ratio(),
        "window_hours": hours,
    }


def digest_recovery_allowed() -> bool:
    """Fail-open: allow digest unless clearly overused."""
    try:
        dep = compute_digest_dependency(hours=24)
        if dep.get("digest_heavy"):
            return False
        dep6 = compute_digest_dependency(hours=6)
        if float(dep6.get("digest_to_publish_ratio") or 0) >= 0.5 and int(
            dep6.get("digest_publishes") or 0,
        ) >= 2:
            return False
    except Exception:
        return True
    return True


def note_digest_recovery_success() -> None:
    try:
        st = load_state()
        n = int(st.get("consecutive_digest_recoveries") or 0) + 1
        save_state(metrics={"consecutive_digest_recoveries": n, "last_digest_recovery_at": _utcnow()})
    except Exception:
        pass


def note_normal_publish() -> None:
    try:
        save_state(metrics={"consecutive_digest_recoveries": 0})
    except Exception:
        pass


def _utcnow() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
