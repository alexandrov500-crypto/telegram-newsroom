from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class OpsCertificationSettings:
    enabled: bool = False
    chaos_enabled: bool = False
    chaos_scheduled: bool = False
    slo_enabled: bool = True
    certification_window_hours: float = 24.0
    certification_min_score: float = 0.85
    longevity_enabled: bool = True
    governance_enabled: bool = True
    mesh_aggregation_enabled: bool = True
    executive_reports_enabled: bool = True
    probe_interval_sec: float = 60.0

    @classmethod
    def from_env(cls) -> OpsCertificationSettings:
        enabled = os.getenv("OPS_CERT_ENABLED", "").lower() in ("1", "true", "yes")
        if not enabled:
            enabled = os.getenv("APP_ENV", "").lower() in ("staging", "production")
        return cls(
            enabled=enabled,
            chaos_enabled=os.getenv("OPS_CHAOS_ENABLED", "").lower() in ("1", "true", "yes"),
            chaos_scheduled=os.getenv("OPS_CHAOS_SCHEDULED", "").lower() in ("1", "true", "yes"),
            slo_enabled=os.getenv("OPS_SLO_ENABLED", "true").lower() not in ("0", "false", "no"),
            certification_window_hours=float(os.getenv("OPS_CERT_WINDOW_HOURS", "24")),
            certification_min_score=float(os.getenv("OPS_CERT_MIN_SCORE", "0.85")),
            longevity_enabled=os.getenv("OPS_LONGEVITY_ENABLED", "true").lower()
            not in ("0", "false", "no"),
            governance_enabled=os.getenv("OPS_GOVERNANCE_ENABLED", "true").lower()
            not in ("0", "false", "no"),
            mesh_aggregation_enabled=os.getenv("OPS_MESH_AGG", "true").lower()
            not in ("0", "false", "no"),
            executive_reports_enabled=os.getenv("OPS_EXEC_REPORTS", "true").lower()
            not in ("0", "false", "no"),
            probe_interval_sec=float(os.getenv("OPS_CERT_PROBE_INTERVAL_SEC", "60")),
        )
