from __future__ import annotations

from typing import Any

from bot.editorial.flow_health.state import load_state


def verify_restart_survivability(
    *,
    metrics: dict[str, Any] | None = None,
    loop_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Restart & recovery calmness — deterministic checks only."""
    st = metrics if metrics is not None else load_state()
    snapshot = loop_snapshot or {}

    try:
        from bot.observability.loop_registry import get_loop_registry

        snapshot = get_loop_registry().snapshot()
    except Exception:
        pass

    recovery_count = int(st.get("recovery_activation_count") or 0)
    recovery_active = bool(st.get("recovery_activated_at"))

    recoveries = sum(int((m or {}).get("recoveries") or 0) for m in snapshot.values())
    errors = sum(1 for m in snapshot.values() if m.get("last_error"))

    health = 0.85
    if recovery_active:
        health -= 0.15
    if errors > 2:
        health -= 0.2
    if recovery_count > 50:
        health -= 0.1

    return {
        "runtime_restart_health": round(max(0.0, min(1.0, health)), 3),
        "recovery_activation_count": recovery_count,
        "recovery_active": recovery_active,
        "loop_recovery_ticks": recoveries,
        "loop_error_count": errors,
        "restart_survivability_ok": health >= 0.6 and not recovery_active,
    }
