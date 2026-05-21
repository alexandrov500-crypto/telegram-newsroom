"""Economic operational modes (AI depth, retention, snapshot cadence)."""

from __future__ import annotations

import json
import os
import time
from enum import Enum
from pathlib import Path
from typing import Any

from ops.economics.paths import economic_mode_path


class EconomicMode(str, Enum):
    LOW_COST = "low_cost"
    BALANCED = "balanced"
    HIGH_QUALITY = "high_quality"
    CRISIS_MODE = "crisis_mode"
    BURST_MODE = "burst_mode"


_PROFILES: dict[str, dict[str, Any]] = {
    "low_cost": {
        "ai_depth": "minimal",
        "ranking_breadth": 0.6,
        "retention_multiplier": 0.8,
        "snapshot_cadence_hours": 24,
        "max_tokens_per_hour_scale": 0.5,
    },
    "balanced": {
        "ai_depth": "standard",
        "ranking_breadth": 1.0,
        "retention_multiplier": 1.0,
        "snapshot_cadence_hours": 12,
        "max_tokens_per_hour_scale": 1.0,
    },
    "high_quality": {
        "ai_depth": "full",
        "ranking_breadth": 1.2,
        "retention_multiplier": 1.1,
        "snapshot_cadence_hours": 6,
        "max_tokens_per_hour_scale": 1.25,
    },
    "crisis_mode": {
        "ai_depth": "breaking_only",
        "ranking_breadth": 0.5,
        "retention_multiplier": 0.7,
        "snapshot_cadence_hours": 4,
        "max_tokens_per_hour_scale": 0.35,
    },
    "burst_mode": {
        "ai_depth": "standard",
        "ranking_breadth": 1.0,
        "retention_multiplier": 1.0,
        "snapshot_cadence_hours": 8,
        "max_tokens_per_hour_scale": 1.5,
    },
}


def load_economic_mode(runtime_dir: str) -> EconomicMode:
    raw = os.getenv("RUNTIME_ECONOMIC_MODE", "").strip().lower()
    path = economic_mode_path(runtime_dir)
    if path.is_file():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            raw = str(data.get("mode") or raw).strip().lower()
        except (OSError, json.JSONDecodeError):
            pass
    try:
        return EconomicMode(raw or "balanced")
    except ValueError:
        return EconomicMode.BALANCED


def set_economic_mode(runtime_dir: str, mode: EconomicMode, *, reason: str = "") -> None:
    path = economic_mode_path(runtime_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "mode": mode.value,
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "reason": reason[:200],
                "profile": _PROFILES.get(mode.value, {}),
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def economic_mode_payload(runtime_dir: str) -> dict[str, Any]:
    mode = load_economic_mode(runtime_dir)
    return {
        "mode": mode.value,
        "profile": _PROFILES.get(mode.value, {}),
        "reloadable": True,
        "env_override": os.getenv("RUNTIME_ECONOMIC_MODE", ""),
    }
