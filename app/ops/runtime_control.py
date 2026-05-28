"""Operator runtime control modes (persisted, explicit transitions only)."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Any

from utils.structured_log import log_event

logger = logging.getLogger(__name__)

_lock = threading.RLock()
_cache: tuple[str, float, RuntimeControlMode] | None = None


class RuntimeControlMode(str, Enum):
    NORMAL = "normal"
    SOFT_DEGRADED = "soft_degraded"
    HARD_DEGRADED = "hard_degraded"
    TEXT_ONLY = "text_only"
    PAUSED = "paused"


_PUBLISH_BLOCKED = frozenset({RuntimeControlMode.PAUSED})


def _control_path(runtime_dir: str) -> Path:
    return Path(runtime_dir).expanduser().resolve() / "runtime_control.json"


def _env_mode() -> RuntimeControlMode | None:
    raw = os.getenv("RUNTIME_CONTROL_MODE", "").strip().lower()
    if not raw:
        return None
    try:
        return RuntimeControlMode(raw)
    except ValueError:
        logger.warning("RUNTIME_CONTROL_MODE=%r invalid; ignored", raw)
        return None


def infer_mode_from_env() -> RuntimeControlMode:
    """Map burn-in / media env to a single control mode (deterministic, no hidden tiers)."""
    env = _env_mode()
    if env is not None:
        return env
    text_only = os.getenv("MEDIA_PIPELINE_ENABLED", "true").strip().lower() in {
        "0",
        "false",
        "no",
        "off",
    }
    if text_only:
        return RuntimeControlMode.TEXT_ONLY
    hard = os.getenv("BURNIN_OPENAI_ALWAYS_FALLBACK", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    } and os.getenv("BURNIN_SOFT_GOVERNANCE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if hard:
        return RuntimeControlMode.HARD_DEGRADED
    soft = os.getenv("BURNIN_OPENAI_ALWAYS_FALLBACK", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if soft:
        return RuntimeControlMode.SOFT_DEGRADED
    return RuntimeControlMode.NORMAL


def _read_file(runtime_dir: str) -> RuntimeControlMode | None:
    path = _control_path(runtime_dir)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        raw = str(data.get("mode") or "").strip().lower()
        return RuntimeControlMode(raw) if raw else None
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def resolve_runtime_control(runtime_dir: str) -> tuple[RuntimeControlMode, str]:
    """
    Precedence: explicit RUNTIME_CONTROL_MODE env > persisted file > burn-in/media inference.
    GLOBAL_PUBLISH_PAUSE does not mutate mode; publish gate checks it separately.
    """
    env_override = _env_mode()
    if env_override is not None:
        return env_override, "env"
    persisted = _read_file(runtime_dir)
    if persisted is not None:
        return persisted, "persisted"
    return infer_mode_from_env(), "inferred_env"


def load_runtime_control(runtime_dir: str) -> RuntimeControlMode:
    global _cache
    with _lock:
        if _cache and _cache[0] == runtime_dir and (time.time() - _cache[1]) < 2.0:
            return _cache[2]
        mode, _source = resolve_runtime_control(runtime_dir)
        _cache = (runtime_dir, time.time(), mode)
        return mode


def persist_runtime_control(runtime_dir: str, mode: RuntimeControlMode, *, reason: str = "") -> None:
    path = _control_path(runtime_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "mode": mode.value,
        "reason": (reason or "")[:240],
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    global _cache
    with _lock:
        _cache = (runtime_dir, time.time(), mode)


def set_runtime_control(runtime_dir: str, mode: RuntimeControlMode, *, reason: str = "") -> None:
    previous = load_runtime_control(runtime_dir)
    persist_runtime_control(runtime_dir, mode, reason=reason)
    if previous != mode:
        log_event(
            logger,
            "runtime.degraded_mode_changed",
            previous=previous.value,
            mode=mode.value,
            reason=(reason or "")[:120],
        )
        logger.info(
            "runtime control %s -> %s (%s)",
            previous.value,
            mode.value,
            reason or "manual",
        )


def sync_runtime_control_from_env(runtime_dir: str) -> RuntimeControlMode:
    """Align persisted control with env on boot (env wins except GLOBAL_PUBLISH_PAUSE overlay)."""
    inferred = infer_mode_from_env()
    current = _read_file(runtime_dir)
    env_explicit = _env_mode() is not None or os.getenv("GLOBAL_PUBLISH_PAUSE", "").strip()
    if current is None:
        set_runtime_control(runtime_dir, inferred, reason="boot_initial")
        return inferred
    if env_explicit and current != inferred:
        set_runtime_control(runtime_dir, inferred, reason="env_sync_at_boot")
        return inferred
    return load_runtime_control(runtime_dir)


def publish_allowed_by_control(runtime_dir: str) -> bool:
    if os.getenv("GLOBAL_PUBLISH_PAUSE", "").strip().lower() in {"1", "true", "yes", "on"}:
        return False
    return load_runtime_control(runtime_dir) not in _PUBLISH_BLOCKED


def media_pipeline_allowed(runtime_dir: str) -> bool:
    return load_runtime_control(runtime_dir) != RuntimeControlMode.TEXT_ONLY


def runtime_control_payload(runtime_dir: str) -> dict[str, Any]:
    mode, source = resolve_runtime_control(runtime_dir)
    return {
        "mode": mode.value,
        "source": source,
        "precedence": "env>persisted>inferred_env",
        "publish_allowed": publish_allowed_by_control(runtime_dir),
        "media_pipeline_allowed": media_pipeline_allowed(runtime_dir),
        "global_publish_pause": os.getenv("GLOBAL_PUBLISH_PAUSE", "").strip().lower()
        in {"1", "true", "yes", "on"},
    }
