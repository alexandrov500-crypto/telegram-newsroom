"""Local execution lease with heartbeat (same-host duplicate protection + ops visibility)."""

from __future__ import annotations

import json
import os
import socket
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = __import__("logging").getLogger(__name__)

LEASE_FILE = "execution_lease.json"
DEFAULT_TTL_SEC = 90.0


@dataclass(frozen=True, slots=True)
class ExecutionLease:
    owner_id: str
    runtime_id: str
    node_role: str
    hostname: str
    heartbeat_unix: float
    acquired_unix: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "owner_id": self.owner_id,
            "runtime_id": self.runtime_id,
            "node_role": self.node_role,
            "hostname": self.hostname,
            "heartbeat_unix": self.heartbeat_unix,
            "acquired_unix": self.acquired_unix,
            "age_sec": round(max(0.0, time.time() - self.heartbeat_unix), 2),
        }


def _lease_path(runtime_state_dir: str) -> Path:
    return Path(runtime_state_dir) / LEASE_FILE


def _read_raw(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def read_lease(runtime_state_dir: str) -> ExecutionLease | None:
    raw = _read_raw(_lease_path(runtime_state_dir))
    if not raw:
        return None
    try:
        return ExecutionLease(
            owner_id=str(raw.get("owner_id") or ""),
            runtime_id=str(raw.get("runtime_id") or ""),
            node_role=str(raw.get("node_role") or "worker"),
            hostname=str(raw.get("hostname") or ""),
            heartbeat_unix=float(raw.get("heartbeat_unix") or 0),
            acquired_unix=float(raw.get("acquired_unix") or 0),
        )
    except (TypeError, ValueError):
        return None


def lease_ttl_sec() -> float:
    raw = os.getenv("EXECUTION_LEASE_TTL_SEC", "").strip()
    if raw:
        try:
            return max(30.0, min(float(raw), 3600.0))
        except ValueError:
            pass
    return DEFAULT_TTL_SEC


def is_lease_stale(lease: ExecutionLease | None, *, now: float | None = None) -> bool:
    if lease is None:
        return True
    now = now if now is not None else time.time()
    return (now - lease.heartbeat_unix) > lease_ttl_sec()


def try_acquire_lease(
    runtime_state_dir: str,
    *,
    owner_id: str,
    runtime_id: str,
    node_role: str,
    force: bool = False,
) -> tuple[bool, ExecutionLease | None]:
    """Acquire or refresh lease. Returns (acquired, current_lease)."""
    path = _lease_path(runtime_state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    now = time.time()
    existing = read_lease(runtime_state_dir)
    if existing and not force:
        if existing.owner_id != owner_id and not is_lease_stale(existing, now=now):
            return False, existing
    lease = ExecutionLease(
        owner_id=owner_id,
        runtime_id=runtime_id,
        node_role=node_role,
        hostname=socket.gethostname()[:128],
        heartbeat_unix=now,
        acquired_unix=existing.acquired_unix if existing and existing.owner_id == owner_id else now,
    )
    path.write_text(json.dumps(lease.to_dict(), indent=2), encoding="utf-8")
    return True, lease


def heartbeat_lease(runtime_state_dir: str, *, owner_id: str, runtime_id: str, node_role: str) -> bool:
    ok, _ = try_acquire_lease(
        runtime_state_dir,
        owner_id=owner_id,
        runtime_id=runtime_id,
        node_role=node_role,
        force=False,
    )
    return ok


def release_lease(runtime_state_dir: str, *, owner_id: str) -> bool:
    path = _lease_path(runtime_state_dir)
    existing = read_lease(runtime_state_dir)
    if existing is None:
        return True
    if existing.owner_id != owner_id:
        return False
    try:
        path.unlink()
        return True
    except OSError:
        return False


def clear_stale_lease(runtime_state_dir: str) -> bool:
    existing = read_lease(runtime_state_dir)
    if existing is None:
        return False
    if not is_lease_stale(existing):
        return False
    try:
        _lease_path(runtime_state_dir).unlink()
        return True
    except OSError:
        return False


def write_execution_intent(runtime_state_dir: str, *, role: str, reason: str = "") -> Path:
    path = Path(runtime_state_dir) / "execution_intent.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "role": role,
        "reason": reason[:200],
        "requested_at_unix": time.time(),
        "hostname": socket.gethostname()[:128],
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def clear_execution_intent(runtime_state_dir: str) -> None:
    p = Path(runtime_state_dir) / "execution_intent.json"
    if p.is_file():
        p.unlink()
