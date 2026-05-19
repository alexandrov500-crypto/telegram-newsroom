from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class OperationalMemorySettings:
    enabled: bool = False
    retention_days: int = 90
    prediction_enabled: bool = True
    drift_enabled: bool = True
    seasonality_enabled: bool = True
    auto_incident_capture: bool = True
    queue_spike_threshold: int = 150
    retry_storm_threshold: float = 0.15

    @classmethod
    def from_env(cls) -> OperationalMemorySettings:
        enabled = os.getenv("OPERATIONAL_MEMORY_ENABLED", "").lower() in ("1", "true", "yes")
        if not enabled:
            enabled = os.getenv("WEEK1_STABILIZATION_ENABLED", "").lower() in ("1", "true", "yes")
        return cls(
            enabled=enabled,
            retention_days=int(os.getenv("OPMEM_RETENTION_DAYS", "90")),
            prediction_enabled=os.getenv("OPMEM_PREDICTION", "true").lower()
            not in ("0", "false", "no"),
            drift_enabled=os.getenv("OPMEM_DRIFT", "true").lower() not in ("0", "false", "no"),
            seasonality_enabled=os.getenv("OPMEM_SEASONALITY", "true").lower()
            not in ("0", "false", "no"),
            auto_incident_capture=os.getenv("OPMEM_AUTO_INCIDENTS", "true").lower()
            not in ("0", "false", "no"),
            queue_spike_threshold=int(os.getenv("OPMEM_QUEUE_SPIKE", "150")),
            retry_storm_threshold=float(os.getenv("OPMEM_RETRY_STORM", "0.15")),
        )
