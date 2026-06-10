"""Runtime persistence for editorial stability layer."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def _path(runtime_dir: str | None) -> Path:
    base = Path(runtime_dir or "var/runtime").expanduser().resolve()
    base.mkdir(parents=True, exist_ok=True)
    return base / "editorial_stability_state.json"


def _default() -> dict[str, Any]:
    return {
        "version": 1,
        "cluster_buffer": [],
        "recent_source_types": [],
        "daily_stats": {},
        "silence_events": [],
        "last_synthesis_ts": 0.0,
    }


def load_state(runtime_dir: str | None) -> dict[str, Any]:
    p = _path(runtime_dir)
    if not p.is_file():
        return _default()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return _default()
    if not isinstance(data, dict):
        return _default()
    data.setdefault("version", 1)
    data.setdefault("cluster_buffer", [])
    data.setdefault("recent_source_types", [])
    data.setdefault("daily_stats", {})
    return data


def save_state(runtime_dir: str | None, data: dict[str, Any]) -> None:
    p = _path(runtime_dir)
    data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
