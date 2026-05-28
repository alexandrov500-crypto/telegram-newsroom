"""Pipeline checkpoint persistence (/data/runtime/checkpoints/latest.json)."""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

from ops.pipeline.paths import checkpoint_latest_path

_lock = threading.RLock()
_VERSION = 1


def _runtime_id() -> str:
    try:
        from app.runtime_lifecycle import runtime_id

        return runtime_id()
    except Exception:
        return "unknown"


def load_checkpoint(runtime_dir: str | None) -> dict[str, Any]:
    path = checkpoint_latest_path(runtime_dir)
    backup = path.with_suffix(".json.bak")
    for candidate in (path, backup):
        if not candidate.is_file():
            continue
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                data.setdefault("version", _VERSION)
                return data
        except (OSError, json.JSONDecodeError):
            continue
    return {
        "version": _VERSION,
        "updated_at": None,
        "runtime_id": None,
        "last_tick_id": None,
        "last_stable_state": "boot",
        "inflight": [],
        "published_idempotency_keys": [],
    }


def save_checkpoint(runtime_dir: str | None, patch: dict[str, Any]) -> dict[str, Any]:
    with _lock:
        data = load_checkpoint(runtime_dir)
        data.update(patch)
        data["version"] = _VERSION
        data["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        data["runtime_id"] = _runtime_id()
        path = checkpoint_latest_path(runtime_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        payload = json.dumps(data, ensure_ascii=False, indent=2, default=str)
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, path)
        bak = path.with_suffix(".json.bak")
        try:
            bak.write_text(payload, encoding="utf-8")
        except OSError:
            pass
        return data
