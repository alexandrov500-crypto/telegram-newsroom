from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

_identity: RuntimeIdentity | None = None
_watchdog_active: bool = False


@dataclass(frozen=True)
class RuntimeIdentity:
    runtime_instance_id: str
    pid: int
    runtime_profile: str
    started_at: str

    def log_line(self) -> str:
        return (
            f"Runtime instance: id={self.runtime_instance_id} "
            f"pid={self.pid} profile={self.runtime_profile}"
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def alert_context(self) -> dict[str, object]:
        return {
            "runtime_instance_id": self.runtime_instance_id,
            "runtime_pid": self.pid,
            "runtime_profile": self.runtime_profile,
        }


def generate_runtime_instance_id(profile: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    slug = profile.replace("_", "")[:16] or "runtime"
    return f"{slug}_{ts}_{os.getpid()}"


def create_runtime_identity(profile: str) -> RuntimeIdentity:
    return RuntimeIdentity(
        runtime_instance_id=generate_runtime_instance_id(profile),
        pid=os.getpid(),
        runtime_profile=profile,
        started_at=datetime.now(timezone.utc).isoformat(),
    )


def install_runtime_identity(identity: RuntimeIdentity) -> RuntimeIdentity:
    global _identity
    _identity = identity
    return identity


def get_runtime_identity() -> RuntimeIdentity | None:
    return _identity


def set_watchdog_active(active: bool) -> None:
    global _watchdog_active
    _watchdog_active = active


def is_watchdog_active() -> bool:
    return _watchdog_active


def runtime_identity_snapshot() -> dict[str, object]:
    ident = get_runtime_identity()
    if ident is None:
        return {"status": "unavailable"}
    return {
        "status": "ok",
        **ident.to_dict(),
        "watchdog_active": _watchdog_active,
    }
