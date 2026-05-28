"""Per-source circuit breaker (CLOSED / OPEN / HALF_OPEN)."""

from __future__ import annotations

import json
import os
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Any

from ops.pipeline.paths import runtime_root

_lock = threading.RLock()

_CONSEC_FAIL_OPEN = int(os.getenv("OPS_SOURCE_CIRCUIT_CONSEC_FAIL", "5"))
_FAIL_RATE_OPEN = float(os.getenv("OPS_SOURCE_CIRCUIT_FAIL_RATE", "0.5"))
_OPEN_COOLDOWN_SEC = float(os.getenv("OPS_SOURCE_CIRCUIT_OPEN_SEC", "900"))
_WINDOW = int(os.getenv("OPS_SOURCE_CIRCUIT_WINDOW", "100"))


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


def _path(runtime_dir: str | None) -> Path:
    return runtime_root(runtime_dir) / "source_circuits.json"


class SourceCircuitBreaker:
    def __init__(self, runtime_dir: str | None) -> None:
        self._runtime_dir = runtime_dir

    def _load(self) -> dict[str, Any]:
        p = _path(self._runtime_dir)
        if not p.is_file():
            return {"version": 1, "sources": {}}
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"version": 1, "sources": {}}
        data.setdefault("sources", {})
        return data

    def _save(self, data: dict[str, Any]) -> None:
        p = _path(self._runtime_dir)
        p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def _row(self, data: dict[str, Any], source: str) -> dict[str, Any]:
        key = (source or "").strip().lower()
        sources = data.setdefault("sources", {})
        row = sources.get(key)
        if not isinstance(row, dict):
            row = {
                "state": CircuitState.CLOSED.value,
                "consecutive_failures": 0,
                "window": [],
                "opened_at_unix": 0.0,
            }
            sources[key] = row
        return row

    def allow_fetch(self, source: str) -> tuple[bool, str]:
        with _lock:
            data = self._load()
            row = self._row(data, source)
            state = CircuitState(str(row.get("state") or CircuitState.CLOSED.value))
            opened = float(row.get("opened_at_unix") or 0)
            now = time.time()
            if state == CircuitState.OPEN:
                if now - opened >= _OPEN_COOLDOWN_SEC:
                    row["state"] = CircuitState.HALF_OPEN.value
                    self._save(data)
                    return True, "half_open_probe"
                return False, "circuit_open"
            return True, state.value

    def record_success(self, source: str) -> None:
        with _lock:
            data = self._load()
            row = self._row(data, source)
            row["consecutive_failures"] = 0
            row["state"] = CircuitState.CLOSED.value
            w = list(row.get("window") or [])
            w.append({"ok": True, "ts": time.time()})
            row["window"] = w[-_WINDOW:]
            self._save(data)
            try:
                from utils.source_reputation import record_publish_for_channels

                record_publish_for_channels([source], runtime_dir=self._runtime_dir)
            except Exception:
                pass

    def record_failure(self, source: str, *, reason: str = "") -> None:
        with _lock:
            data = self._load()
            row = self._row(data, source)
            cf = int(row.get("consecutive_failures") or 0) + 1
            row["consecutive_failures"] = cf
            w = list(row.get("window") or [])
            w.append({"ok": False, "ts": time.time(), "reason": (reason or "")[:120]})
            row["window"] = w[-_WINDOW:]
            fails = sum(1 for x in row["window"] if not x.get("ok"))
            rate = fails / max(1, len(row["window"]))
            if cf >= _CONSEC_FAIL_OPEN or rate >= _FAIL_RATE_OPEN:
                row["state"] = CircuitState.OPEN.value
                row["opened_at_unix"] = time.time()
            self._save(data)
            try:
                from utils.source_reputation import record_reject_for_channels

                record_reject_for_channels([source], runtime_dir=self._runtime_dir)
            except Exception:
                pass
