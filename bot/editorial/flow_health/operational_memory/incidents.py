from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bot.editorial.flow_health.operational_memory.retention import evict_incidents
from bot.editorial.flow_health.state import load_state, save_state

_CALM = "CALM_RECOVERY"


def _utc_day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _days_since(iso_day: str) -> int:
    try:
        then = datetime.strptime(iso_day, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - then).days)
    except ValueError:
        return 0


def touch_incident_memory(
    *,
    signatures: list[str],
    recovery_mode: str,
    resolved: bool = False,
) -> dict[str, Any]:
    """Update bounded operational_memory.incidents — compressed, not audit log."""
    try:
        st = load_state()
        mem: dict[str, Any] = dict(st.get("operational_memory") or {})
        incidents: list[dict[str, Any]] = list(mem.get("incidents") or [])
        today = _utc_day()
        touch = dict(mem.get("touch") or {})
        seen_today = set(touch.get("signatures") or [])

        for sig in signatures:
            if sig in seen_today:
                continue
            found = None
            for inc in incidents:
                if inc.get("signature") == sig:
                    found = inc
                    break
            if found:
                found["occurrences"] = int(found.get("occurrences") or 0) + 1
                found["last_seen_days"] = 0
                found["last_seen_day"] = today
                if resolved:
                    found["resolved"] = True
                    found["resolution_mode"] = recovery_mode
            else:
                incidents.append(
                    {
                        "signature": sig,
                        "first_seen_day": today,
                        "last_seen_day": today,
                        "first_seen_days": 0,
                        "last_seen_days": 0,
                        "occurrences": 1,
                        "resolved": resolved,
                        "resolution_mode": recovery_mode if resolved else None,
                    },
                )

        active_sigs = set(signatures)
        for inc in incidents:
            first = str(inc.get("first_seen_day", today))
            last = str(inc.get("last_seen_day", today))
            inc["first_seen_days"] = _days_since(first)
            inc["last_seen_days"] = _days_since(last)
            if inc.get("signature") not in active_sigs and not inc.get("resolved"):
                if inc["last_seen_days"] >= 7 and recovery_mode == _CALM:
                    inc["resolved"] = True
                    inc["resolution_mode"] = _CALM

        incidents = evict_incidents(incidents)
        touch["day"] = today
        touch["signatures"] = sorted(set(touch.get("signatures") or []) | set(signatures))
        mem["incidents"] = incidents
        mem["touch"] = touch
        save_state(metrics={"operational_memory": mem})
        return mem
    except Exception:
        return {}
