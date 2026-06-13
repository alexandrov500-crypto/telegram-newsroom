"""Persist bounded autonomous tuning overrides (runtime-only, not .env)."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_STATE_FILE = "autonomous_growth_tuning.json"

# env_key -> (min, max, step)
TUNING_BOUNDS: dict[str, tuple[float, float, float]] = {
    "UEOS_PUBLISH_THRESHOLD": (65.0, 78.0, 1.0),
    "EDITORIAL_ANTI_PAUSE_GAP_MINUTES": (40.0, 90.0, 5.0),
    "PUBLISH_CHANNEL_MIN_INTERVAL_SEC": (30.0, 120.0, 5.0),
}


def _state_path(runtime_dir: str) -> Path:
    return Path(runtime_dir) / _STATE_FILE


def load_tuning_state(runtime_dir: str) -> dict[str, Any]:
    path = _state_path(runtime_dir)
    if not path.is_file():
        return {"overrides": {}, "history": [], "updated_at": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"overrides": {}, "history": []}
    except (OSError, json.JSONDecodeError):
        return {"overrides": {}, "history": [], "updated_at": None}


def save_tuning_state(runtime_dir: str, state: dict[str, Any]) -> None:
    path = _state_path(runtime_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.now(UTC).isoformat()
    path.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def _coerce_env_value(key: str, value: float) -> str:
    if key.endswith("_SEC") or "THRESHOLD" in key:
        return str(int(round(value)))
    if "MINUTES" in key:
        return str(int(round(value)))
    return str(value)


def clamp_override(key: str, value: float) -> float:
    lo, hi, _ = TUNING_BOUNDS[key]
    return max(lo, min(hi, value))


def apply_tuning_overrides_to_env(runtime_dir: str | None = None) -> dict[str, str]:
    """Apply saved overrides to os.environ (idempotent). Returns active overrides."""
    if os.getenv("AUTONOMOUS_GROWTH_TUNING_ENABLED", "true").strip().lower() in {"0", "false", "no", "off"}:
        return {}
    rd = runtime_dir or os.getenv("RUNTIME_STATE_DIR", "./var/runtime")
    state = load_tuning_state(rd)
    overrides = state.get("overrides") if isinstance(state.get("overrides"), dict) else {}
    applied: dict[str, str] = {}
    for key, raw in overrides.items():
        if key not in TUNING_BOUNDS:
            continue
        try:
            val = clamp_override(key, float(raw))
        except (TypeError, ValueError):
            continue
        sval = _coerce_env_value(key, val)
        os.environ[key] = sval
        applied[key] = sval
    return applied


def set_override(
    runtime_dir: str,
    key: str,
    value: float,
    *,
    reason: str,
) -> dict[str, Any]:
    if key not in TUNING_BOUNDS:
        raise ValueError(f"unsupported tuning key: {key}")
    state = load_tuning_state(runtime_dir)
    overrides = dict(state.get("overrides") or {})
    clamped = clamp_override(key, value)
    overrides[key] = clamped
    history = list(state.get("history") or [])
    history.append(
        {
            "at": datetime.now(UTC).isoformat(),
            "key": key,
            "value": clamped,
            "reason": reason,
        }
    )
    state["overrides"] = overrides
    state["history"] = history[-48:]
    save_tuning_state(runtime_dir, state)
    apply_tuning_overrides_to_env(runtime_dir)
    return state
