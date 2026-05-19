from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class PlatformSettings:
    enabled: bool = False
    plugins: bool = True
    workflows: bool = True
    graph: bool = True
    policy_engine: bool = True
    observability_hub: bool = True
    internal_gateway: bool = True
    ecosystem_governance: bool = True
    probe_interval_sec: float = 120.0

    @classmethod
    def from_env(cls) -> PlatformSettings:
        enabled = os.getenv("PLATFORM_ENABLED", "").lower() in ("1", "true", "yes")
        if not enabled:
            enabled = os.getenv("OPS_EVOLUTION_ENABLED", "").lower() in ("1", "true", "yes")
        return cls(
            enabled=enabled,
            plugins=os.getenv("PLATFORM_PLUGINS", "true").lower() not in ("0", "false", "no"),
            workflows=os.getenv("PLATFORM_WORKFLOWS", "true").lower() not in ("0", "false", "no"),
            graph=os.getenv("PLATFORM_GRAPH", "true").lower() not in ("0", "false", "no"),
            policy_engine=os.getenv("PLATFORM_POLICY", "true").lower() not in ("0", "false", "no"),
            observability_hub=os.getenv("PLATFORM_OBS_HUB", "true").lower()
            not in ("0", "false", "no"),
            internal_gateway=os.getenv("PLATFORM_GATEWAY", "true").lower()
            not in ("0", "false", "no"),
            ecosystem_governance=os.getenv("PLATFORM_GOVERNANCE", "true").lower()
            not in ("0", "false", "no"),
            probe_interval_sec=float(os.getenv("PLATFORM_PROBE_SEC", "120")),
        )
