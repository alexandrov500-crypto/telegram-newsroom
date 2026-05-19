from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class WorkerRole(str, Enum):
    INGEST = "ingest-worker"
    COGNITION = "cognition-worker"
    PUBLISH = "publish-worker"
    OPERATOR = "operator-worker"
    METRICS = "metrics-worker"
    RECOVERY = "recovery-worker"


@dataclass
class WorkerDescriptor:
    role: WorkerRole
    node_id: str
    queues: tuple[str, ...]
    heartbeat_interval_sec: float = 30.0
    last_heartbeat: float = field(default_factory=time.monotonic)
    status: str = "starting"
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_stale(self, *, multiplier: float = 3.0) -> bool:
        return (time.monotonic() - self.last_heartbeat) > self.heartbeat_interval_sec * multiplier

    def heartbeat(self, *, status: str = "healthy") -> None:
        self.last_heartbeat = time.monotonic()
        self.status = status


class WorkerMeshRegistry:
    """Horizontal worker registration and ownership."""

    def __init__(self) -> None:
        self._workers: dict[str, WorkerDescriptor] = {}

    def register(
        self,
        role: WorkerRole,
        node_id: str,
        *,
        queues: tuple[str, ...] = (),
    ) -> WorkerDescriptor:
        key = f"{role.value}:{node_id}"
        desc = WorkerDescriptor(role=role, node_id=node_id, queues=queues)
        self._workers[key] = desc
        return desc

    def heartbeat(self, role: WorkerRole, node_id: str, *, status: str = "healthy") -> None:
        key = f"{role.value}:{node_id}"
        w = self._workers.get(key)
        if w is not None:
            w.heartbeat(status=status)

    def stale_workers(self) -> list[WorkerDescriptor]:
        return [w for w in self._workers.values() if w.is_stale()]

    def snapshot(self) -> list[dict[str, Any]]:
        return [
            {
                "role": w.role.value,
                "node_id": w.node_id,
                "status": w.status,
                "queues": list(w.queues),
                "age_sec": round(time.monotonic() - w.last_heartbeat, 1),
            }
            for w in self._workers.values()
        ]
