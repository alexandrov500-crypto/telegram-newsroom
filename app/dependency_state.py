"""Runtime dependency health model (healthy / degraded / unavailable)."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DependencyStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class AggregateStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass(slots=True)
class DependencyRecord:
    status: DependencyStatus
    detail: str = ""
    recovery_hint: str = ""

    def to_dict(self) -> dict[str, str]:
        out: dict[str, str] = {"status": self.status.value}
        if self.detail:
            out["detail"] = self.detail
        if self.recovery_hint:
            out["recovery_hint"] = self.recovery_hint
        return out


@dataclass(slots=True)
class RuntimeDependencyState:
    """Mutable registry updated at startup and exposed on /health."""

    database: DependencyRecord = field(
        default_factory=lambda: DependencyRecord(DependencyStatus.HEALTHY)
    )
    telegram_api: DependencyRecord = field(
        default_factory=lambda: DependencyRecord(DependencyStatus.HEALTHY)
    )
    openai: DependencyRecord = field(
        default_factory=lambda: DependencyRecord(DependencyStatus.HEALTHY)
    )
    telethon: DependencyRecord = field(
        default_factory=lambda: DependencyRecord(DependencyStatus.HEALTHY)
    )
    ai_pipeline_enabled: bool = True
    collector_enabled: bool = True
    startup_complete: bool = False
    polling_active: bool = False
    polling_retry_count: int = 0

    def set_dependency(
        self,
        name: str,
        *,
        status: DependencyStatus,
        detail: str = "",
        recovery_hint: str = "",
    ) -> None:
        rec = DependencyRecord(status=status, detail=detail, recovery_hint=recovery_hint)
        if name == "database":
            self.database = rec
        elif name == "telegram_api":
            self.telegram_api = rec
        elif name == "openai":
            self.openai = rec
        elif name == "telethon":
            self.telethon = rec
        else:
            raise KeyError(f"unknown dependency: {name}")

    def aggregate_status(self) -> AggregateStatus:
        records = (
            self.database,
            self.telegram_api,
            self.openai,
            self.telethon,
        )
        if any(r.status == DependencyStatus.UNAVAILABLE for r in records):
            if self.database.status == DependencyStatus.UNAVAILABLE:
                return AggregateStatus.UNHEALTHY
            return AggregateStatus.DEGRADED
        if any(r.status == DependencyStatus.DEGRADED for r in records):
            return AggregateStatus.DEGRADED
        return AggregateStatus.HEALTHY

    def dependencies_dict(self) -> dict[str, dict[str, str]]:
        return {
            "database": self.database.to_dict(),
            "telegram_api": self.telegram_api.to_dict(),
            "openai": self.openai.to_dict(),
            "telethon": self.telethon.to_dict(),
        }

    def health_payload(self) -> dict[str, Any]:
        tg = self.telegram_api.to_dict()
        tg["polling_active"] = self.polling_active
        tg["retry_count"] = self.polling_retry_count
        deps = self.dependencies_dict()
        deps["telegram_api"] = tg
        return {
            "status": self.aggregate_status().value,
            "service": "newsroom",
            "startup_complete": self.startup_complete,
            "ai_pipeline_enabled": self.ai_pipeline_enabled,
            "collector_enabled": self.collector_enabled,
            "dependencies": deps,
        }


_REGISTRY: RuntimeDependencyState | None = None


def get_dependency_state() -> RuntimeDependencyState:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = RuntimeDependencyState()
    return _REGISTRY


def reset_dependency_state() -> None:
    global _REGISTRY
    _REGISTRY = RuntimeDependencyState()
