"""Explicit runtime operational modes (reloadable, publish-aware)."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_lock = threading.RLock()
_mode_cache: tuple[str, float] | None = None


class OperationalMode(str, Enum):
    BOOTSTRAP = "bootstrap"
    DEGRADED = "degraded"
    SOAK = "soak"
    PRODUCTION = "production"
    MAINTENANCE = "maintenance"
    RECOVERY = "recovery"
    READ_ONLY = "read_only"
    FIRST_POST_DEBUG = "first_post_debug"


_PUBLISH_BLOCKED = frozenset({
    OperationalMode.MAINTENANCE,
    OperationalMode.RECOVERY,
    OperationalMode.READ_ONLY,
    OperationalMode.BOOTSTRAP,
})

_SCHEDULER_BLOCKED = frozenset({
    OperationalMode.MAINTENANCE,
    OperationalMode.RECOVERY,
    OperationalMode.READ_ONLY,
})


def _mode_path(runtime_dir: str) -> Path:
    return Path(runtime_dir).expanduser().resolve() / "operational_mode.json"


def _infer_from_settings(settings: Any) -> OperationalMode:
    raw = os.getenv("RUNTIME_OPERATIONAL_MODE", "").strip().lower()
    if raw:
        try:
            return OperationalMode(raw)
        except ValueError:
            pass
    if getattr(settings, "soak_test", False):
        return OperationalMode.SOAK
    if getattr(settings, "dry_run", False) and getattr(settings, "deployment_profile", "") == "production":
        return OperationalMode.DEGRADED
    return OperationalMode.PRODUCTION


def _mode_from_env() -> OperationalMode | None:
    raw = os.getenv("RUNTIME_OPERATIONAL_MODE", "").strip().lower()
    if not raw:
        return None
    try:
        return OperationalMode(raw)
    except ValueError:
        logger.warning("RUNTIME_OPERATIONAL_MODE=%r is invalid; ignoring env override", raw)
        return None


def _mode_from_file(runtime_dir: str) -> OperationalMode | None:
    path = _mode_path(runtime_dir)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        m = str(data.get("mode") or "").strip().lower()
        if m:
            return OperationalMode(m)
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return None


def sync_operational_mode_from_env(runtime_dir: str) -> OperationalMode | None:
    """Persist explicit RUNTIME_OPERATIONAL_MODE from .env so volume JSON matches operator intent."""
    env_mode = _mode_from_env()
    if env_mode is None:
        return None
    persist_operational_mode(runtime_dir, env_mode, reason="env_sync_at_boot")
    logger.info("operational_mode synced from RUNTIME_OPERATIONAL_MODE=%s", env_mode.value)
    return env_mode


def load_operational_mode(runtime_dir: str, settings: Any | None = None) -> OperationalMode:
    """
    Resolve operational mode.

    Explicit ``RUNTIME_OPERATIONAL_MODE`` in the process environment wins over a stale
    ``operational_mode.json`` left by rollback/recovery tooling (otherwise the scheduler
    can stay disabled while .env says production).
    """
    global _mode_cache
    with _lock:
        env_mode = _mode_from_env()
        file_mode = _mode_from_file(runtime_dir)
        if env_mode is not None:
            if file_mode is not None and file_mode != env_mode:
                logger.warning(
                    "RUNTIME_OPERATIONAL_MODE=%s overrides persisted operational_mode.json mode=%s",
                    env_mode.value,
                    file_mode.value,
                )
            _mode_cache = (env_mode.value, time.time())
            return env_mode
        if file_mode is not None:
            _mode_cache = (file_mode.value, time.time())
            return file_mode
        if settings is not None:
            mode = _infer_from_settings(settings)
            persist_operational_mode(runtime_dir, mode, reason="inferred_at_load")
            return mode
        return OperationalMode.PRODUCTION


def persist_operational_mode(runtime_dir: str, mode: OperationalMode, *, reason: str = "") -> None:
    global _mode_cache
    path = _mode_path(runtime_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "mode": mode.value,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "reason": reason[:200],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    with _lock:
        _mode_cache = (mode.value, time.time())


def set_operational_mode(runtime_dir: str, mode: OperationalMode, *, reason: str = "") -> None:
    persist_operational_mode(runtime_dir, mode, reason=reason)


def operational_mode_payload(runtime_dir: str, settings: Any | None = None) -> dict[str, Any]:
    mode = load_operational_mode(runtime_dir, settings)
    return {
        "mode": mode.value,
        "publish_allowed": publish_allowed(mode, settings),
        "scheduler_allowed": scheduler_allowed(mode),
        "reloadable": True,
    }


def publish_allowed(mode: OperationalMode | None = None, settings: Any | None = None) -> bool:
    m = mode or (load_operational_mode(settings.runtime_state_dir, settings) if settings else OperationalMode.PRODUCTION)
    if m in _PUBLISH_BLOCKED:
        return False
    if settings is not None and getattr(settings, "dry_run", False):
        return True
    return True


def scheduler_allowed(mode: OperationalMode | None = None) -> bool:
    m = mode or OperationalMode.PRODUCTION
    return m not in _SCHEDULER_BLOCKED
