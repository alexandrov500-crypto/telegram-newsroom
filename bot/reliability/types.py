from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class HealthState(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"
    FAILED = "FAILED"


class SubsystemName(str, Enum):
    INGEST = "ingest"
    COGNITION = "cognition"
    PUBLISH = "publish"
    SCHEDULER = "scheduler"
    TELEGRAM_API = "telegram_api"
    OPENAI_API = "openai_api"


class IncidentSeverity(str, Enum):
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    FATAL = "FATAL"

    @property
    def rank(self) -> int:
        return {
            IncidentSeverity.INFO: 0,
            IncidentSeverity.WARN: 1,
            IncidentSeverity.ERROR: 2,
            IncidentSeverity.CRITICAL: 3,
            IncidentSeverity.FATAL: 4,
        }[self]


class PublishMode(str, Enum):
    DRY_RUN = "DRY_RUN"
    SHADOW = "SHADOW"
    LIMITED_PRODUCTION = "LIMITED_PRODUCTION"
    FULL_PRODUCTION = "FULL_PRODUCTION"


@dataclass
class SubsystemHealth:
    name: SubsystemName
    state: HealthState
    score: float
    last_heartbeat_sec: float
    error_rate: float
    retries_hour: int
    detail: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeHealthSnapshot:
    overall_state: HealthState
    health_score: float
    degraded_mode: bool
    subsystems: tuple[SubsystemHealth, ...]
    queue_depth: int
    errors_per_hour: float
    retries_per_hour: int
    stuck_pipeline: bool
    publish_mode: PublishMode
    uptime_sec: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_state": self.overall_state.value,
            "health_score": round(self.health_score, 4),
            "degraded_mode": self.degraded_mode,
            "queue_depth": self.queue_depth,
            "errors_per_hour": round(self.errors_per_hour, 2),
            "retries_per_hour": self.retries_per_hour,
            "stuck_pipeline": self.stuck_pipeline,
            "publish_mode": self.publish_mode.value,
            "uptime_sec": round(self.uptime_sec, 1),
            "subsystems": [
                {
                    "name": s.name.value,
                    "state": s.state.value,
                    "score": round(s.score, 3),
                    "last_heartbeat_sec": round(s.last_heartbeat_sec, 1),
                    "error_rate": round(s.error_rate, 4),
                    "detail": s.detail,
                }
                for s in self.subsystems
            ],
        }
