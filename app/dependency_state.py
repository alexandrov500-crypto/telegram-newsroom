"""Runtime dependency health model (healthy / degraded / unavailable)."""
from __future__ import annotations

import os
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
    execution_profile: dict[str, Any] = field(default_factory=dict)

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
        circuit_snapshot = get_openai_circuit().snapshot()
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

        execution: dict[str, Any] = dict(self.execution_profile or {})
        try:
            from app.ops.runtime.execution_lease import read_lease

            rd = os.getenv("RUNTIME_STATE_DIR", "var/runtime")
            lease = read_lease(rd)
            if lease:
                execution["lease"] = lease.to_dict()
        except Exception:
            pass

        pipeline_hint: dict[str, Any] = {}
        desk_hint: dict[str, Any] = {}
        try:
            from app.reliability.pipeline_health_hint import pipeline_health_hint

            pipeline_hint = pipeline_health_hint()
        except Exception:
            pass
        try:
            from app.editorial.desk_starvation import desk_health_snapshot

            desk_hint = desk_health_snapshot()
        except Exception:
            pass

        staging: dict[str, Any] = {}
        try:
            from app.observability.staging_health import staging_health_snapshot

            staging = staging_health_snapshot()
        except Exception:
            pass

        async_runtime: dict[str, Any] = {}
        try:
            from app.runtime.task_orchestrator import orchestrator_health_snapshot

            async_runtime = orchestrator_health_snapshot()
        except Exception:
            pass

        circuit_allows = True
        reconcile_extra: dict[str, Any] = {}
        try:
            from app.openai_circuit import get_openai_circuit
            from app.recovery.pipeline_overrides import upstream_pipeline_state
            from app.recovery.pipeline_state_reconciler import reconciliation_health_extra
            from app.state.pipeline_decision_engine import apply_pipeline_decision
            from app.state.pipeline_execution_wrapper import pipeline_evaluation_only

            circuit = get_openai_circuit()
            circuit_allows = circuit.allow_request()
            with pipeline_evaluation_only():
                pd = apply_pipeline_decision(source="health_payload")
            ai_live = pd.should_execute
            reconcile_extra = reconciliation_health_extra()
            reconcile_extra["pipeline_decision"] = pd.to_dict()
            upstream_state = upstream_pipeline_state(
                ctx_ai_enabled=pd.should_execute,
                circuit_allows=circuit_allows,
            )
            reconcile_extra["ai_pipeline_enabled_cache_deprecated"] = self.ai_pipeline_enabled
        except Exception:
            ai_live = self.ai_pipeline_enabled
            upstream_state = "unknown"

        payload: dict[str, Any] = {
            "status": self.aggregate_status().value,
            "service": "newsroom",
            "startup_complete": self.startup_complete,
            "execution": execution,
            "ai_pipeline_enabled": ai_live,
            "should_execute_pipeline": ai_live,
            "ai_pipeline_enabled_derived": ai_live,
            "ai_pipeline_enabled_cache_deprecated": self.ai_pipeline_enabled,
            "pipeline_decision": reconcile_extra.get("pipeline_decision") or reconcile_extra,
            "pipeline_execution_decision": reconcile_extra,
            "upstream_pipeline_state": upstream_state,
            "pipeline_reconcile": reconcile_extra,
            "collector_enabled": self.collector_enabled,
            "dependencies": deps,
            "runtime_slo": slo,
            "pipeline": pipeline_hint,
            "desk": desk_hint,
            "staging": staging,
            "runtime": {
                "runtime_id": runtime_id(),
                "uptime_sec": round(uptime_sec(), 2),
                "git_sha": prov.git_sha,
                "build_version": prov.build_version,
                "queue_depth": queue_depth,
                "last_successful_collect_at": activity.get("last_successful_collect_at"),
                "last_successful_ai_at": activity.get("last_successful_ai_at"),
                "last_successful_publish_at": activity.get("last_successful_publish_at"),
                "openai_circuit_state": circuit_snapshot.get("state"),
                "openai_disabled": circuit_snapshot.get("openai_disabled"),
                "polling_status": polling_status,
            },
            "event_loop_lag_ms": async_runtime.get("event_loop_lag_ms", 0),
            "active_task_count": async_runtime.get("active_task_count", 0),
            "hung_task_count": async_runtime.get("hung_task_count", 0),
            "scheduler_generation": async_runtime.get("scheduler_generation", ""),
            "async_integrity_ok": async_runtime.get("async_integrity_ok", True),
            "async_runtime": async_runtime,
        }
        try:
            from app.runtime.telegram_connectivity import build_telegram_connectivity_snapshot

            payload["telegram_connectivity"] = build_telegram_connectivity_snapshot()
            if payload["telegram_connectivity"].get("collect_cycle", {}).get("collect_stalled"):
                payload["async_integrity_ok"] = False
        except Exception:
            payload["telegram_connectivity"] = {"error": "snapshot_unavailable"}
        return payload


_REGISTRY: RuntimeDependencyState | None = None


def get_dependency_state() -> RuntimeDependencyState:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = RuntimeDependencyState()
    return _REGISTRY


def reset_dependency_state() -> None:
    global _REGISTRY
    _REGISTRY = RuntimeDependencyState()
