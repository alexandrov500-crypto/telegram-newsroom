from __future__ import annotations

from typing import Any


def verify_scheduler_survivability(
    *,
    loop_snapshot: dict[str, Any] | None = None,
    pulse: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Scheduler continuity & publish path — advisory snapshot."""
    stalled: list[str] = []
    snapshot = loop_snapshot or {}

    try:
        from bot.observability.loop_registry import get_loop_registry

        snapshot = get_loop_registry().snapshot()
        stalled = [
            name
            for name, meta in snapshot.items()
            if meta.get("stalled") and meta.get("watchdog_eligible")
        ]
    except Exception:
        pass

    total = len(snapshot) or 1
    stalled_ratio = len(stalled) / total
    scheduler_stability = round(max(0.0, 1.0 - stalled_ratio * 2), 3)

    pulse = pulse or {}
    funnel = pulse.get("publish_funnel") or pulse.get("funnel") or {}
    publish_ok = not funnel.get("starvation", {}).get("detected") if isinstance(funnel, dict) else True
    if pulse.get("publish_continuity_ok") is not None:
        publish_ok = bool(pulse.get("publish_continuity_ok"))

    digest_age = None
    for name, meta in snapshot.items():
        if "digest" in name.lower():
            digest_age = meta.get("age_sec")
            break

    return {
        "scheduler_stability": scheduler_stability,
        "publish_continuity_ok": publish_ok,
        "stalled_loops": stalled[:8],
        "loop_count": total,
        "digest_scheduler_age_sec": digest_age,
        "scheduler_continuity_ok": scheduler_stability >= 0.7 and len(stalled) == 0,
    }
