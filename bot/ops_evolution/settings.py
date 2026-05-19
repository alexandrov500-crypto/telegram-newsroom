from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class OpsEvolutionSettings:
    enabled: bool = False
    memory: bool = True
    strategy: bool = True
    cognition_governance: bool = True
    assistant: bool = True
    long_horizon_analytics: bool = True
    maintenance_orchestration: bool = True
    maturity_model: bool = True
    evolution_safety: bool = True
    memory_max_active: int = 500
    probe_interval_sec: float = 120.0

    @classmethod
    def from_env(cls) -> OpsEvolutionSettings:
        enabled = os.getenv("OPS_EVOLUTION_ENABLED", "").lower() in ("1", "true", "yes")
        if not enabled:
            enabled = os.getenv("POST_GA_ENABLED", "").lower() in ("1", "true", "yes")
        return cls(
            enabled=enabled,
            memory=os.getenv("OPS_EVOLUTION_MEMORY", "true").lower() not in ("0", "false", "no"),
            strategy=os.getenv("OPS_EVOLUTION_STRATEGY", "true").lower() not in ("0", "false", "no"),
            cognition_governance=os.getenv("OPS_EVOLUTION_COGNITION", "true").lower()
            not in ("0", "false", "no"),
            assistant=os.getenv("OPS_EVOLUTION_ASSISTANT", "true").lower()
            not in ("0", "false", "no"),
            long_horizon_analytics=os.getenv("OPS_EVOLUTION_ANALYTICS", "true").lower()
            not in ("0", "false", "no"),
            maintenance_orchestration=os.getenv("OPS_EVOLUTION_MAINTENANCE", "true").lower()
            not in ("0", "false", "no"),
            maturity_model=os.getenv("OPS_EVOLUTION_MATURITY", "true").lower()
            not in ("0", "false", "no"),
            evolution_safety=os.getenv("OPS_EVOLUTION_SAFETY", "true").lower()
            not in ("0", "false", "no"),
            memory_max_active=int(os.getenv("OPS_EVOLUTION_MEMORY_MAX", "500")),
            probe_interval_sec=float(os.getenv("OPS_EVOLUTION_PROBE_SEC", "120")),
        )
