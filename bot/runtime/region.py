from __future__ import annotations

import logging
from dataclasses import dataclass

from bot.policy.evaluator import PolicyContext
from bot.policy.runtime import PolicyRuntime

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RegionRoute:
    region: str
    score: float
    failover: bool
    reason: str


class RegionOrchestrator:
    """Region-aware workflow routing and quorum checks."""

    def __init__(self, *, node_region: str, policy: PolicyRuntime | None = None) -> None:
        self._home_region = node_region
        self._policy = policy

    def region_scores(self, topology_regions: dict[str, dict]) -> dict[str, float]:
        return {k: float(v.get("score", 0.5)) for k, v in topology_regions.items()}

    def choose_region(
        self,
        workflow_class: str,
        *,
        preferred: str | None = None,
        region_health: dict[str, float] | None = None,
    ) -> RegionRoute:
        target = preferred or self._home_region
        health = region_health or {self._home_region: 1.0}
        score = health.get(target, 0.5)
        if self._policy is not None:
            ctx = PolicyContext(
                node_region=self._home_region,
                target_region=target,
                region_health=health,
                workflow_class=workflow_class,
            )
            decision = self._policy.decide("regional_route", ctx)
            if decision.metadata.get("to"):
                return RegionRoute(
                    region=str(decision.metadata["to"]),
                    score=health.get(str(decision.metadata["to"]), score),
                    failover=True,
                    reason=decision.reason,
                )
            if not decision.allowed:
                return RegionRoute(region=target, score=score, failover=False, reason=decision.reason)
        if score < 0.4:
            for alt, alt_score in sorted(health.items(), key=lambda x: -x[1]):
                if alt_score >= 0.4:
                    return RegionRoute(
                        region=alt,
                        score=alt_score,
                        failover=True,
                        reason=f"failover from {target}",
                    )
        return RegionRoute(region=target, score=score, failover=False, reason="preferred region ok")

    def quorum_ok(self, region_health: dict[str, float], *, min_per_region: int = 1) -> bool:
        """At least one region above failover threshold."""
        if not region_health:
            return True
        threshold = 0.4
        if self._policy is not None:
            threshold = float(
                self._policy.evaluator.document.regional_failover.get(
                    "failover_score_threshold",
                    0.4,
                ),
            )
        healthy_regions = sum(1 for s in region_health.values() if s >= threshold)
        return healthy_regions >= min_per_region
