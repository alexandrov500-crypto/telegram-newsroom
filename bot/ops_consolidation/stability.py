from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def architecture_stability_phase_enabled() -> bool:
    raw = os.getenv("ARCHITECTURE_STABILITY_PHASE", "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def stability_phase_rules() -> list[str]:
    if not architecture_stability_phase_enabled():
        return []
    return [
        "New major subsystems require ops_consolidation contract entry",
        "Experimental features must be env-gated (default off)",
        "Telemetry schema changes need backward-compatible readers",
        "Prefer extending existing owners over parallel tables",
        "Weekly /ops_consolidation review required before new ops_* tables",
    ]


def check_subsystem_addition(name: str, *, experimental: bool = False) -> dict[str, Any]:
    """Advisory gate — logs warning, never blocks runtime."""
    enabled = architecture_stability_phase_enabled()
    result: dict[str, Any] = {
        "stability_phase": enabled,
        "subsystem": name,
        "allowed": True,
        "advisory": None,
    }
    if not enabled:
        return result
    if experimental:
        result["advisory"] = f"'{name}' should remain behind feature flag during stability phase"
    else:
        result["advisory"] = (
            f"'{name}' addition flagged — document contract in ops_consolidation/contracts.py"
        )
    logger.info("event=stability_phase_check subsystem=%s experimental=%s", name, experimental)
    return result


def stability_snapshot() -> dict[str, Any]:
    return {
        "enabled": architecture_stability_phase_enabled(),
        "rules": stability_phase_rules(),
        "env": "ARCHITECTURE_STABILITY_PHASE=true",
    }
