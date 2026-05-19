from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from bot.policy.types import ClusterPolicyDocument, PolicyAction, PolicyDecision, WorkflowQoSClass

logger = logging.getLogger(__name__)


@dataclass
class PolicyContext:
    """Runtime signals for policy evaluation."""

    node_id: str = "local"
    node_role: str = "all"
    node_region: str = "global"
    node_status: str = "healthy"
    queue_backlog: int = 0
    stream_lag_sec: float = 0.0
    dlq_count: int = 0
    workflow_stalled: int = 0
    region_health: dict[str, float] | None = None
    publishes_last_minute: int = 0
    envelope_version: int = 1
    in_maintenance_window: bool = False
    degradation_mode: str = "normal"
    workflow_class: str = WorkflowQoSClass.DIGEST.value
    target_region: str | None = None

    def region_score(self, region: str) -> float:
        if self.region_health is None:
            return 1.0
        return float(self.region_health.get(region, 0.5))


class PolicyEvaluator:
    """Evaluates declarative cluster policies against live context."""

    def __init__(self, doc: ClusterPolicyDocument) -> None:
        self._doc = doc

    @property
    def document(self) -> ClusterPolicyDocument:
        return self._doc

    def evaluate_node_admission(self, ctx: PolicyContext) -> PolicyDecision:
        rules = self._doc.node_admission
        if rules.get("reject_draining") and ctx.node_status == "draining":
            return self._decision(PolicyAction.DENY, False, "node is draining")
        min_ver = int(rules.get("min_capability_version", 1))
        if ctx.envelope_version < min_ver:
            return self._decision(
                PolicyAction.DENY,
                False,
                f"envelope version {ctx.envelope_version} < {min_ver}",
            )
        return self._decision(PolicyAction.ALLOW, True, "node admission ok")

    def evaluate_workflow_start(self, ctx: PolicyContext) -> PolicyDecision:
        throttle = self._doc.workflow_throttle
        backlog_limit = int(throttle.get("global_backlog_threshold", 500))
        if ctx.queue_backlog >= backlog_limit:
            wc = ctx.workflow_class
            if wc in (WorkflowQoSClass.ANALYTICS.value, WorkflowQoSClass.BACKFILL.value):
                return self._decision(
                    PolicyAction.DEFER,
                    False,
                    f"backlog {ctx.queue_backlog} >= {backlog_limit}",
                )
            if wc == WorkflowQoSClass.DIGEST.value and ctx.queue_backlog >= backlog_limit * 1.2:
                return self._decision(
                    PolicyAction.THROTTLE,
                    False,
                    "digest throttled under extreme backlog",
                )
        if ctx.in_maintenance_window and ctx.workflow_class not in (
            WorkflowQoSClass.BREAKING.value,
            WorkflowQoSClass.PUBLISH.value,
        ):
            return self._decision(PolicyAction.DEFER, False, "maintenance window active")
        if ctx.degradation_mode in ("read_only", "replay_only", "operator_only"):
            if ctx.workflow_class not in (WorkflowQoSClass.BREAKING.value,):
                return self._decision(
                    PolicyAction.DEFER,
                    False,
                    f"degradation mode {ctx.degradation_mode}",
                )
        return self._decision(PolicyAction.ALLOW, True, "workflow permitted")

    def evaluate_publish(self, ctx: PolicyContext) -> PolicyDecision:
        limits = self._doc.publish_limits
        max_pm = int(limits.get("max_per_minute", 30))
        burst = int(limits.get("burst_allowance", 5))
        if ctx.publishes_last_minute > max_pm + burst:
            return self._decision(
                PolicyAction.THROTTLE,
                False,
                f"publish rate {ctx.publishes_last_minute} > {max_pm}+{burst}",
            )
        if ctx.degradation_mode == "read_only":
            return self._decision(PolicyAction.DENY, False, "read-only mode")
        safe_backlog = int(limits.get("publish_safe_backlog", 400))
        if ctx.queue_backlog > safe_backlog and ctx.workflow_class != WorkflowQoSClass.BREAKING.value:
            return self._decision(
                PolicyAction.THROTTLE,
                False,
                f"publish-safe backlog gate {ctx.queue_backlog}",
            )
        return self._decision(PolicyAction.ALLOW, True, "publish permitted")

    def evaluate_federation_sync(self, ctx: PolicyContext) -> PolicyDecision:
        fed = self._doc.federation_sync
        if not fed.get("enabled", True):
            return self._decision(PolicyAction.DEFER, False, "federation sync disabled")
        threshold = float(fed.get("pause_below_region_score", 0.3))
        score = ctx.region_score(ctx.node_region)
        if score < threshold:
            return self._decision(
                PolicyAction.DEFER,
                False,
                f"region score {score:.2f} < {threshold}",
            )
        if ctx.degradation_mode == "degraded_federation":
            return self._decision(PolicyAction.DEFER, False, "degraded federation mode")
        return self._decision(PolicyAction.ALLOW, True, "federation sync ok")

    def evaluate_regional_route(
        self,
        ctx: PolicyContext,
        *,
        workflow_region: str,
    ) -> PolicyDecision:
        failover = self._doc.regional_failover
        preferred = list(failover.get("preferred_regions", ["global"]))
        threshold = float(failover.get("failover_score_threshold", 0.4))
        score = ctx.region_score(workflow_region)
        if score >= threshold:
            return self._decision(
                PolicyAction.ALLOW,
                True,
                f"region {workflow_region} score {score:.2f}",
                metadata={"region": workflow_region},
            )
        for alt in preferred:
            if alt != workflow_region and ctx.region_score(alt) >= threshold:
                return self._decision(
                    PolicyAction.REDIRECT,
                    True,
                    f"failover {workflow_region} -> {alt}",
                    metadata={"from": workflow_region, "to": alt},
                )
        return self._decision(
            PolicyAction.DEFER,
            False,
            f"no healthy region for {workflow_region}",
        )

    def lease_weight(self, workflow_class: str) -> float:
        digest = self._doc.digest_priority
        if workflow_class == WorkflowQoSClass.BREAKING.value:
            return float(digest.get("lease_weight_breaking", 3.0))
        if workflow_class == WorkflowQoSClass.DIGEST.value:
            return float(digest.get("lease_weight_digest", 1.0))
        return 1.0

    def in_maintenance_window(self, now: datetime | None = None) -> bool:
        now = now or datetime.now(timezone.utc)
        for window in self._doc.maintenance_windows:
            try:
                start_h = int(window.get("start_hour_utc", -1))
                end_h = int(window.get("end_hour_utc", -1))
                if start_h <= now.hour < end_h:
                    return True
            except (TypeError, ValueError):
                continue
        return False

    def _decision(
        self,
        action: PolicyAction,
        allowed: bool,
        reason: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> PolicyDecision:
        return PolicyDecision(
            action=action,
            allowed=allowed,
            reason=reason,
            policy_id=self._doc.policy_id,
            policy_version=self._doc.version,
            metadata=metadata or {},
        )
