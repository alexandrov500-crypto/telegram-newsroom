from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4


class WorkflowStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STALLED = "stalled"
    RECOVERING = "recovering"


class WorkflowType(str, Enum):
    DIGEST = "digest"
    ENRICHMENT = "enrichment"
    MEDIA_RENDER = "media_render"
    PUBLISH = "publish"
    FEDERATION_SYNC = "federation_sync"


@dataclass
class WorkflowCheckpoint:
    workflow_id: str
    step_name: str
    data: dict[str, Any]
    sequence_num: int = 0
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )


@dataclass
class WorkflowRun:
    workflow_id: str
    workflow_type: str
    correlation_id: str
    status: str
    holder_node_id: str
    lease_expires_at: str | None = None
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
    )

    @staticmethod
    def new_id(workflow_type: str) -> str:
        return f"{workflow_type}:{uuid4().hex[:12]}"
