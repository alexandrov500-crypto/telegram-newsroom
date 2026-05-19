from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any

from bot.operational_memory.models import IncidentRecord
from bot.operational_memory.repository import OperationalMemoryRepository


_INCIDENT_TYPES = frozenset(
    {
        "queue_spike",
        "floodwait_cascade",
        "backlog_incident",
        "source_instability",
        "queue_congestion",
        "engagement_collapse",
        "publish_slowdown",
        "retry_storm",
        "operator_intervention",
        "rollback_event",
    },
)


class IncidentMemoryStore:
    """Append-only operational incident history."""

    def __init__(self, repository: OperationalMemoryRepository) -> None:
        self.repository = repository
        self._open: dict[str, str] = {}

    def record(
        self,
        incident_type: str,
        *,
        severity: str,
        signals: dict[str, Any],
        subsystems: list[str] | None = None,
        root_cause: str = "",
        operator_actions: list[str] | None = None,
    ) -> str:
        if incident_type not in _INCIDENT_TYPES:
            incident_type = "queue_spike"
        iid = str(uuid.uuid4())
        fp = self._fingerprint_hash(incident_type, signals)
        rec = IncidentRecord(
            incident_id=iid,
            incident_type=incident_type,
            severity=severity,
            started_at=datetime.now(timezone.utc).isoformat(),
            affected_subsystems=subsystems or self._infer_subsystems(signals),
            metrics_snapshot=dict(signals),
            survivability_score=signals.get("survivability_score"),
            confidence_trend=signals.get("confidence_trend"),
            root_cause_candidate=root_cause or self._infer_root_cause(incident_type, signals),
            operator_actions=operator_actions or [],
            fingerprint_hash=fp,
        )
        self.repository.append_incident(rec)
        self._open[incident_type] = iid
        return iid

    def resolve(self, incident_type: str, *, recovery_sec: float, actions: list[str]) -> None:
        iid = self._open.pop(incident_type, None)
        if iid:
            self.repository.close_incident(
                iid,
                recovery_duration_sec=recovery_sec,
                operator_actions=actions,
            )

    def detect_from_signals(self, signals: dict[str, Any]) -> list[dict[str, str]]:
        """Auto-capture open incidents from live telemetry."""
        opened: list[dict[str, str]] = []
        q = int(signals.get("queue_depth", 0))
        threshold = int(signals.get("queue_spike_threshold", 150))
        retry_thr = float(signals.get("retry_storm_threshold", 0.15))
        if q > threshold:
            if "queue_spike" not in self._open:
                iid = self.record("queue_spike", severity="warning", signals=signals)
                opened.append({"incident_id": iid, "incident_type": "queue_spike"})
        if float(signals.get("retry_amplification", 0)) > retry_thr:
            if "retry_storm" not in self._open:
                iid = self.record("retry_storm", severity="high", signals=signals)
                opened.append({"incident_id": iid, "incident_type": "retry_storm"})
        if float(signals.get("stabilization_risk", 0)) > 0.65:
            if "operator_intervention" not in self._open:
                iid = self.record(
                    "operator_intervention",
                    severity="medium",
                    signals=signals,
                )
                opened.append(
                    {"incident_id": iid, "incident_type": "operator_intervention"},
                )
        if signals.get("rollback_in_progress"):
            iid = self.record("rollback_event", severity="critical", signals=signals)
            opened.append({"incident_id": iid, "incident_type": "rollback_event"})
        return opened

    @staticmethod
    def _fingerprint_hash(incident_type: str, signals: dict[str, Any]) -> str:
        material = f"{incident_type}:{signals.get('rollout_stage')}:{int(signals.get('queue_depth', 0) // 50)}"
        return hashlib.sha256(material.encode()).hexdigest()[:16]

    @staticmethod
    def _infer_subsystems(signals: dict[str, Any]) -> list[str]:
        out: list[str] = []
        if int(signals.get("queue_depth", 0)) > 0:
            out.append("queue")
        if float(signals.get("telegram_pressure", 0)) > 0.3:
            out.append("telegram")
        if float(signals.get("cognition_latency_ms", 0)) > 2000:
            out.append("cognition")
        return out or ["platform"]

    @staticmethod
    def _infer_root_cause(incident_type: str, signals: dict[str, Any]) -> str:
        if incident_type == "floodwait_cascade":
            return "telegram_rate_limit"
        if incident_type in ("queue_spike", "queue_congestion", "backlog_incident"):
            return "ingest_pressure"
        if incident_type == "retry_storm":
            return "downstream_instability"
        if incident_type == "engagement_collapse":
            return "audience_fatigue"
        return "operational_stress"
