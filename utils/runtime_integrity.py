"""Read-only integrity helpers for ``RUNTIME_STATE_DIR`` JSON (production-lite)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from editorial.intelligence_store import load_json, operational_timeline_path, suppression_state_path


def validate_operational_timeline(runtime_dir: str | None) -> list[str]:
    """Return human-readable issues (empty list = OK)."""
    issues: list[str] = []
    path = operational_timeline_path(runtime_dir)
    if not path.is_file():
        return issues
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        issues.append("operational_timeline.json: invalid_json_on_disk")
        return issues
    data = load_json(path, {"version": 1, "events": []})
    ver = data.get("version")
    if ver not in (1, None):
        issues.append(f"operational_timeline.json: unexpected version {ver!r}")
    evs = data.get("events") or []
    if not isinstance(evs, list):
        issues.append("operational_timeline.json: events is not a list")
        return issues
    now = time.time()
    for i, ev in enumerate(evs[:500]):
        if not isinstance(ev, dict):
            issues.append(f"timeline event[{i}]: not an object")
            continue
        ts = ev.get("ts")
        if ts is not None:
            try:
                t = float(ts)
                if t > now + 86400 * 365:
                    issues.append(f"timeline event[{i}]: ts far in future")
            except (TypeError, ValueError):
                issues.append(f"timeline event[{i}]: invalid ts")
    return issues


def validate_suppression_state(runtime_dir: str | None) -> list[str]:
    issues: list[str] = []
    path = suppression_state_path(runtime_dir)
    if not path.is_file():
        return issues
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        issues.append("suppression_state.json: invalid_json_on_disk")
        return issues
    data = load_json(path, {"version": 1, "entries": {}, "duplicate_burst": {}})
    if not isinstance(data.get("entries"), dict):
        issues.append("suppression_state.json: entries must be an object")
    b = data.get("duplicate_burst")
    if b is not None and not isinstance(b, dict):
        issues.append("suppression_state.json: duplicate_burst must be an object")
    return issues


def validate_event_history(runtime_dir: str | None) -> list[str]:
    from editorial.intelligence_store import event_history_path

    issues: list[str] = []
    path = event_history_path(runtime_dir)
    if not path.is_file():
        return issues
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        issues.append("event_history.json: invalid_json_on_disk")
        return issues
    data = load_json(path, {"version": 1, "events": []})
    ev = data.get("events")
    if not isinstance(ev, list):
        issues.append("event_history.json: events is not a list")
    return issues


def summarize_runtime_state_dir(runtime_dir: str) -> dict[str, Any]:
    """File presence + sizes for ops dashboards (no content)."""
    root = Path(runtime_dir).expanduser()
    out: dict[str, Any] = {"root": str(root), "files": {}}
    if not root.is_dir():
        out["exists"] = False
        return out
    out["exists"] = True
    for rel in (
        "operational_timeline.json",
        "suppression_state.json",
        "publish_cadence.json",
        "topic_memory.json",
        "event_history.json",
    ):
        p = root / rel
        if p.is_file():
            out["files"][rel] = {"bytes": p.stat().st_size}
    return out
