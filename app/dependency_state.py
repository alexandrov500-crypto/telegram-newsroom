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
    polling_conflict_count: int = 0
    conflict_detected: bool = False
    telegram_mode: str = "polling"
    polling_instance_id: str = ""
    bot_id: int | None = None
    bot_username: str = ""
    last_degraded_reason: str = ""
    last_recovery_at_iso: str = ""
    last_recovery_mono: float = 0.0
    consecutive_failures: int = 0

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
        from app.build_provenance import load_build_provenance
        from app.openai_circuit import get_openai_circuit
        from app.runtime_activity import activity_snapshot
        from app.runtime_lifecycle import runtime_id, uptime_sec

        tg = self.telegram_api.to_dict()
        tg["mode"] = self.telegram_mode
        tg["conflict_detected"] = self.conflict_detected
        tg["polling_active"] = self.polling_active
        tg["retry_count"] = self.polling_retry_count
        if self.bot_id is not None:
            tg["bot_id"] = self.bot_id
        if self.bot_username:
            tg["bot_username"] = self.bot_username
        if self.polling_instance_id:
            tg["polling_instance_id"] = self.polling_instance_id
        if self.last_degraded_reason:
            tg["last_degraded_reason"] = self.last_degraded_reason
        if self.last_recovery_at_iso:
            tg["last_recovery_at"] = self.last_recovery_at_iso
        tg["consecutive_failures"] = self.consecutive_failures
        deps = self.dependencies_dict()
        deps["telegram_api"] = tg
        try:
            from app.runtime_slo import slo_snapshot

            slo = slo_snapshot()
        except Exception:
            slo = {}
        prov = load_build_provenance()
        circuit = get_openai_circuit().snapshot()
        activity = activity_snapshot()
        polling_status = {
            "active": self.polling_active,
            "mode": self.telegram_mode,
            "instance_id": self.polling_instance_id or None,
            "retry_count": self.polling_retry_count,
            "conflict_detected": self.conflict_detected,
        }
        try:
            from utils.metrics import export_snapshot

            queue_depth = int((export_snapshot().get("gauges") or {}).get("queue_depth", 0))
        except Exception:
            queue_depth = 0

        return {
            "status": self.aggregate_status().value,
            "service": "newsroom",
            "startup_complete": self.startup_complete,
            "ai_pipeline_enabled": self.ai_pipeline_enabled,
            "collector_enabled": self.collector_enabled,
            "dependencies": deps,
            "runtime_slo": slo,
            "runtime": {
                "runtime_id": runtime_id(),
                "uptime_sec": round(uptime_sec(), 2),
                "git_sha": prov.git_sha,
                "build_version": prov.build_version,
                "queue_depth": queue_depth,
                "last_successful_collect_at": activity.get("last_successful_collect_at"),
                "last_successful_ai_at": activity.get("last_successful_ai_at"),
                "openai_circuit_state": circuit.get("state"),
                "openai_disabled": circuit.get("openai_disabled"),
                "polling_status": polling_status,
            },
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
