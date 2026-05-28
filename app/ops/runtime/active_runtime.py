"""Atomic registration of the active newsroom runtime (owner process)."""

from __future__ import annotations

import json
import logging
import os
import socket
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_FILENAME = "active_runtime.json"


def active_runtime_path(runtime_dir: str) -> Path:
    return Path(runtime_dir).expanduser().resolve() / _FILENAME


def register_active_runtime(
    runtime_dir: str,
    *,
    runtime_id: str,
    pid: int | None = None,
    hostname: str | None = None,
) -> Path:
    """Atomic write: temp file + rename."""
    path = active_runtime_path(runtime_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "runtime_id": runtime_id,
        "pid": pid if pid is not None else os.getpid(),
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "started_at_unix": time.time(),
        "hostname": hostname or socket.gethostname(),
    }
    tmp = path.with_suffix(".json.tmp")
    body = json.dumps(payload, indent=2)
    tmp.write_text(body, encoding="utf-8")
    os.replace(tmp, path)
    logger.info(
        "active runtime registered runtime_id=%s pid=%s path=%s",
        runtime_id,
        payload["pid"],
        path,
    )
    return path


def load_active_runtime(runtime_dir: str) -> dict[str, Any] | None:
    path = active_runtime_path(runtime_dir)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def clear_active_runtime(runtime_dir: str, *, expected_pid: int | None = None) -> None:
    """Remove active runtime marker on shutdown (only if we still own it)."""
    path = active_runtime_path(runtime_dir)
    if not path.is_file():
        return
    if expected_pid is not None:
        data = load_active_runtime(runtime_dir)
        if data and int(data.get("pid", 0)) not in (0, expected_pid):
            logger.warning(
                "active_runtime clear skipped: pid mismatch (ours=%s file=%s)",
                expected_pid,
                data.get("pid"),
            )
            return
    try:
        path.unlink(missing_ok=True)
        logger.info("active runtime cleared path=%s", path)
    except OSError as exc:
        logger.warning("active_runtime clear failed: %s", exc)
