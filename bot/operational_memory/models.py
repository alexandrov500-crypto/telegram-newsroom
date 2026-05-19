from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class IncidentRecord:
    incident_id: str
    incident_type: str
    severity: str
    started_at: str
    affected_subsystems: list[str] = field(default_factory=list)
    metrics_snapshot: dict[str, Any] = field(default_factory=dict)
    survivability_score: float | None = None
    confidence_trend: float | None = None
    root_cause_candidate: str = ""
    operator_actions: list[str] = field(default_factory=list)
    ended_at: str | None = None
    duration_sec: float | None = None
    recovery_duration_sec: float | None = None
    fingerprint_hash: str = ""


@dataclass(frozen=True)
class Fingerprint:
    signature_hash: str
    pattern_name: str
    confidence: float
    recurrence_count: int
    last_seen_at: str
    avg_impact: float
    typical_recovery_sec: float | None = None


@dataclass(frozen=True)
class HorizonRisk:
    horizon: str
    degradation: float
    rollback: float
    queue_overflow: float
    alert_storm: float
    audience_fatigue: float
    explain: dict[str, Any]
