from __future__ import annotations

import os
from typing import Any

from bot.editorial.flow_health.slimming.config_surface import (
    _ADVANCED,
    _CORE,
    _EXPERIMENTAL,
    _FROZEN_DEFAULTS,
    analyze_config_surface,
)


def analyze_configuration_lockdown(
    *,
    config_surface: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Identify configs safe to stop changing — advisory lockdown candidates."""
    surface = config_surface or analyze_config_surface()
    known = _CORE | _ADVANCED | _EXPERIMENTAL | set(_FROZEN_DEFAULTS)
    set_in_env = {k for k in known if os.getenv(k) is not None}

    constant: list[str] = []
    for key, default in _FROZEN_DEFAULTS.items():
        if os.getenv(key, default) == default:
            constant.append(key)

    hard_freeze: list[str] = sorted(_CORE)[:6]
    hotspots: list[str] = []
    if int(surface.get("advanced_touched") or 0) >= 2:
        hotspots.extend(sorted(_ADVANCED)[:4])

    unset_exp = [k for k in _EXPERIMENTAL if os.getenv(k) is None]
    lockdown_candidates = list(dict.fromkeys(constant + hard_freeze + unset_exp[:3]))[:12]

    locked = len(constant) + len(hard_freeze)
    ratio = round(min(1.0, locked / max(1, len(known))), 3)

    return {
        "lockdown_candidates": lockdown_candidates,
        "locked_surface_ratio": ratio,
        "config_hotspots": hotspots,
        "env_keys_set": len(set_in_env),
        "config_surface": surface,
    }
