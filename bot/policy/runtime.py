from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from bot.policy.evaluator import PolicyContext, PolicyEvaluator
from bot.policy.repository import PolicyRepository
from bot.policy.types import ClusterPolicyDocument, PolicyAction, PolicyDecision

logger = logging.getLogger(__name__)


class PolicyRuntime:
    """Hot-reloadable policy runtime with audit and cluster propagation."""

    def __init__(
        self,
        repo: PolicyRepository,
        *,
        node_id: str,
        coordination: Any | None = None,
    ) -> None:
        self._repo = repo
        self._node_id = node_id
        self._coordination = coordination
        self._evaluator: PolicyEvaluator | None = None
        self.reload()

    def reload(self) -> ClusterPolicyDocument | None:
        doc = self._repo.get_active()
        if doc is None:
            logger.warning("event=policy_reload_empty")
            return None
        self._evaluator = PolicyEvaluator(doc)
        logger.info(
            "event=policy_reloaded policy_id=%s version=%d",
            doc.policy_id,
            doc.version,
        )
        return doc

    def hot_reload_from_dict(self, data: dict[str, Any]) -> ClusterPolicyDocument:
        doc = ClusterPolicyDocument.from_dict(data)
        doc.version = max(self._repo.list_versions(doc.policy_id) + [0]) + 1
        self._repo.save(doc, activate=True)
        self.reload()
        self.propagate_cluster(doc)
        return doc

    def propagate_cluster(self, doc: ClusterPolicyDocument | None = None) -> None:
        if self._coordination is None:
            return
        payload = (doc or self._repo.get_active())
        if payload is None:
            return
        try:
            self._coordination.upsert_federated_sync(
                "cluster_policy_active",
                payload.to_dict(),
            )
        except Exception:
            logger.exception("event=policy_propagate_failed")

    def sync_from_cluster(self) -> bool:
        if self._coordination is None:
            return False
        row = self._coordination.get_federated_sync("cluster_policy_active")
        if row is None:
            return False
        remote = row.get("payload", {})
        local = self._repo.get_active()
        if local is not None and remote.get("version", 0) <= local.version:
            return False
        doc = ClusterPolicyDocument.from_dict(remote)
        self._repo.save(doc, activate=True)
        self.reload()
        return True

    @property
    def evaluator(self) -> PolicyEvaluator:
        if self._evaluator is None:
            self.reload()
        assert self._evaluator is not None
        return self._evaluator

    def decide(
        self,
        kind: str,
        ctx: PolicyContext,
        *,
        audit: bool = True,
    ) -> PolicyDecision:
        ev = self.evaluator
        if kind == "node_admission":
            decision = ev.evaluate_node_admission(ctx)
        elif kind == "workflow_start":
            decision = ev.evaluate_workflow_start(ctx)
        elif kind == "publish":
            decision = ev.evaluate_publish(ctx)
        elif kind == "federation_sync":
            decision = ev.evaluate_federation_sync(ctx)
        elif kind == "regional_route":
            decision = ev.evaluate_regional_route(
                ctx,
                workflow_region=ctx.target_region or ctx.node_region,
            )
        else:
            decision = PolicyDecision(
                action=PolicyAction.ALLOW,
                allowed=True,
                reason="unknown kind",
                policy_id=ev.document.policy_id,
                policy_version=ev.document.version,
            )
        if audit:
            self._repo.audit(
                policy_id=decision.policy_id,
                version=decision.policy_version,
                decision=kind,
                action=decision.action.value,
                reason=decision.reason,
                node_id=ctx.node_id,
                context={"allowed": decision.allowed, "workflow_class": ctx.workflow_class},
            )
        return decision


def build_policy_runtime(db_path: Path, *, node_id: str, coordination: Any | None = None) -> PolicyRuntime:
    return PolicyRuntime(PolicyRepository(db_path), node_id=node_id, coordination=coordination)
