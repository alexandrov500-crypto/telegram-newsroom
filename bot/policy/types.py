from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PolicyAction(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    THROTTLE = "throttle"
    REDIRECT = "redirect"
    QUARANTINE = "quarantine"
    DRAIN = "drain"
    DEFER = "defer"


class DegradationMode(str, Enum):
    NORMAL = "normal"
    READ_ONLY = "read_only"
    PUBLISH_SAFE = "publish_safe"
    DEGRADED_FEDERATION = "degraded_federation"
    LOW_MEMORY = "low_memory"
    REPLAY_ONLY = "replay_only"
    OPERATOR_ONLY = "operator_only"


class WorkflowQoSClass(str, Enum):
    BREAKING = "breaking"
    PUBLISH = "publish"
    DIGEST = "digest"
    ENRICHMENT = "enrichment"
    MEDIA = "media"
    FEDERATION = "federation"
    ANALYTICS = "analytics"
    BACKFILL = "backfill"


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    action: PolicyAction
    allowed: bool
    reason: str
    policy_id: str
    policy_version: int
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def explain(self) -> str:
        return f"{self.policy_id}@{self.policy_version}: {self.action.value} — {self.reason}"


@dataclass
class ClusterPolicyDocument:
    """Declarative cluster operations policy (JSON-serializable)."""

    policy_id: str
    version: int
    node_admission: dict[str, Any] = field(default_factory=dict)
    workflow_throttle: dict[str, Any] = field(default_factory=dict)
    regional_failover: dict[str, Any] = field(default_factory=dict)
    publish_limits: dict[str, Any] = field(default_factory=dict)
    retry_escalation: dict[str, Any] = field(default_factory=dict)
    quarantine_rules: dict[str, Any] = field(default_factory=dict)
    federation_sync: dict[str, Any] = field(default_factory=dict)
    digest_priority: dict[str, Any] = field(default_factory=dict)
    maintenance_windows: list[dict[str, Any]] = field(default_factory=list)
    degradation_triggers: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "version": self.version,
            "node_admission": self.node_admission,
            "workflow_throttle": self.workflow_throttle,
            "regional_failover": self.regional_failover,
            "publish_limits": self.publish_limits,
            "retry_escalation": self.retry_escalation,
            "quarantine_rules": self.quarantine_rules,
            "federation_sync": self.federation_sync,
            "digest_priority": self.digest_priority,
            "maintenance_windows": self.maintenance_windows,
            "degradation_triggers": self.degradation_triggers,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ClusterPolicyDocument:
        return cls(
            policy_id=str(data.get("policy_id", "default")),
            version=int(data.get("version", 1)),
            node_admission=dict(data.get("node_admission") or {}),
            workflow_throttle=dict(data.get("workflow_throttle") or {}),
            regional_failover=dict(data.get("regional_failover") or {}),
            publish_limits=dict(data.get("publish_limits") or {}),
            retry_escalation=dict(data.get("retry_escalation") or {}),
            quarantine_rules=dict(data.get("quarantine_rules") or {}),
            federation_sync=dict(data.get("federation_sync") or {}),
            digest_priority=dict(data.get("digest_priority") or {}),
            maintenance_windows=list(data.get("maintenance_windows") or []),
            degradation_triggers=dict(data.get("degradation_triggers") or {}),
        )
