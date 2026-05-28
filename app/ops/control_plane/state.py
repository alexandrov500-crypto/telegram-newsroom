"""Thread-safe runtime OPS state (control plane)."""

from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class OpsState:
    ingestion_enabled: bool = True
    fast_lane_enabled: bool = True
    slow_mode: bool = False
    fast_lane_only: bool = False
    max_queue_depth: int = 256
    publish_rate_limit_per_min: int = 12
    emergency_halt: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "true" if default else "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def default_ops_state() -> OpsState:
    fast = os.getenv("FAST_LANE_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
    return OpsState(
        ingestion_enabled=_env_bool("OPS_INGESTION_ENABLED", True),
        fast_lane_enabled=fast,
        slow_mode=_env_bool("OPS_SLOW_MODE", False),
        fast_lane_only=_env_bool("OPS_FAST_LANE_ONLY", False),
        max_queue_depth=max(8, _env_int("OPS_MAX_QUEUE_DEPTH", 256)),
        publish_rate_limit_per_min=max(1, _env_int("OPS_PUBLISH_RATE_LIMIT_PER_MIN", 12)),
        emergency_halt=_env_bool("OPS_EMERGENCY_HALT", False),
    )


class OpsStateStore:
    """In-process, thread-safe OPS state with optional JSON persistence."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._state = default_ops_state()
        self._runtime_dir: str | None = None
        self._last_pipeline_tick_unix: float = 0.0
        self._publish_timestamps: list[float] = []

    def bind_runtime_dir(self, runtime_dir: str | None) -> None:
        with self._lock:
            self._runtime_dir = runtime_dir
            if runtime_dir:
                loaded = self._load_from_disk(runtime_dir)
                if loaded is not None:
                    self._state = loaded

    def snapshot(self) -> OpsState:
        with self._lock:
            return replace(self._state)

    def patch(self, **kwargs: Any) -> OpsState:
        with self._lock:
            fields = {f.name for f in OpsState.__dataclass_fields__.values()}  # type: ignore[attr-defined]
            clean = {k: v for k, v in kwargs.items() if k in fields}
            if clean:
                self._state = replace(self._state, **clean)
            self._persist()
            return replace(self._state)

    def note_pipeline_tick(self, *, unix: float) -> None:
        with self._lock:
            self._last_pipeline_tick_unix = unix

    def last_pipeline_tick_unix(self) -> float:
        with self._lock:
            return self._last_pipeline_tick_unix

    def record_publish_attempt(self, *, unix: float) -> None:
        with self._lock:
            self._publish_timestamps.append(unix)
            cutoff = unix - 60.0
            self._publish_timestamps = [t for t in self._publish_timestamps if t >= cutoff]

    def publishes_in_last_minute(self) -> int:
        import time

        now = time.time()
        with self._lock:
            return sum(1 for t in self._publish_timestamps if t >= now - 60.0)

    def publish_rate_limited(self) -> bool:
        st = self.snapshot()
        return self.publishes_in_last_minute() >= st.publish_rate_limit_per_min

    def _path(self) -> Path | None:
        if not self._runtime_dir:
            return None
        return Path(self._runtime_dir).expanduser().resolve() / "ops_control_state.json"

    def _load_from_disk(self, runtime_dir: str) -> OpsState | None:
        path = Path(runtime_dir).expanduser().resolve() / "ops_control_state.json"
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            fields = {f.name for f in OpsState.__dataclass_fields__.values()}  # type: ignore[attr-defined]
            return OpsState(**{k: data[k] for k in fields if k in data})
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return None

    def _persist(self) -> None:
        path = self._path()
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                **self._state.to_dict(),
                "updated_at": __import__("time").strftime("%Y-%m-%dT%H:%M:%SZ", __import__("time").gmtime()),
            }
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except OSError:
            pass


_store = OpsStateStore()


def get_ops_store() -> OpsStateStore:
    return _store


def get_ops_state() -> OpsState:
    return _store.snapshot()


def init_ops_state_store(runtime_dir: str | None = None) -> OpsState:
    _store.bind_runtime_dir(runtime_dir)
    return _store.snapshot()


def reset_ops_state_store_for_tests() -> None:
    global _store
    with _store._lock:
        _store = OpsStateStore()
