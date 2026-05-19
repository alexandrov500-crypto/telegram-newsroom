from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LiveOpsSettings:
    """Feature flags for live operations & scale readiness."""

    enabled: bool = False
    event_bus_enabled: bool = True
    worker_mesh_enabled: bool = True
    recovery_on_startup: bool = True
    stability_tracking: bool = True
    cognition_evolution: bool = True
    multi_tenant_registry: bool = True
    probe_interval_sec: float = 30.0
    node_id: str = "local"

    @classmethod
    def from_env(cls) -> LiveOpsSettings:
        enabled = os.getenv("LIVE_OPS_ENABLED", "").lower() in ("1", "true", "yes")
        if not enabled:
            enabled = os.getenv("APP_ENV", "").lower() in ("staging", "production")
        return cls(
            enabled=enabled,
            event_bus_enabled=os.getenv("LIVE_OPS_EVENT_BUS", "true").lower()
            not in ("0", "false", "no"),
            worker_mesh_enabled=os.getenv("LIVE_OPS_WORKER_MESH", "true").lower()
            not in ("0", "false", "no"),
            recovery_on_startup=os.getenv("LIVE_OPS_RECOVERY_STARTUP", "true").lower()
            not in ("0", "false", "no"),
            stability_tracking=os.getenv("LIVE_OPS_STABILITY", "true").lower()
            not in ("0", "false", "no"),
            cognition_evolution=os.getenv("LIVE_OPS_COGNITION_EVOLUTION", "true").lower()
            not in ("0", "false", "no"),
            multi_tenant_registry=os.getenv("LIVE_OPS_TENANCY", "true").lower()
            not in ("0", "false", "no"),
            probe_interval_sec=float(os.getenv("LIVE_OPS_PROBE_INTERVAL_SEC", "30")),
            node_id=os.getenv("NODE_ID", "local"),
        )
