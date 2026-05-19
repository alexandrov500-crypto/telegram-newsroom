from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from bot.rc1.repository import Rc1Repository

logger = logging.getLogger(__name__)


class ActivationStage(str, Enum):
    PRECHECK = "PRECHECK"
    CERTIFICATION = "CERTIFICATION"
    SHADOW_TRAFFIC = "SHADOW_TRAFFIC"
    LIMITED_PUBLIC = "LIMITED_PUBLIC"
    CONTROLLED_EXPANSION = "CONTROLLED_EXPANSION"
    GENERAL_AVAILABILITY = "GENERAL_AVAILABILITY"


_STAGE_ORDER = list(ActivationStage)


_ROLLOUT_MAP = {
    ActivationStage.PRECHECK: "INTERNAL_SHADOW",
    ActivationStage.CERTIFICATION: "INTERNAL_SHADOW",
    ActivationStage.SHADOW_TRAFFIC: "INTERNAL_SHADOW",
    ActivationStage.LIMITED_PUBLIC: "LIMITED_CHANNELS",
    ActivationStage.CONTROLLED_EXPANSION: "LOW_FREQUENCY_PUBLIC",
    ActivationStage.GENERAL_AVAILABILITY: "NORMAL_PRODUCTION",
}


@dataclass(frozen=True)
class StageRequirement:
    check_id: str
    passed: bool
    detail: str


@dataclass
class ActivationTransition:
    allowed: bool
    next_stage: ActivationStage | None
    requirements: tuple[StageRequirement, ...]
    rollback_point: str


@dataclass
class PublicActivationOrchestrator:
    """Formal go-live stage machine with sign-off and snapshots."""

    repository: Rc1Repository

    def current_stage(self) -> ActivationStage:
        row = self.repository.get_activation()
        if not row:
            return ActivationStage.PRECHECK
        try:
            return ActivationStage(row["stage"])
        except ValueError:
            return ActivationStage.PRECHECK

    def evaluate_next(
        self,
        *,
        config_ok: bool = True,
        certified: bool = False,
        go_live_confidence: float = 0.0,
        slo_ok: bool = True,
        operator_signoff: bool = False,
    ) -> ActivationTransition:
        current = self.current_stage()
        idx = _STAGE_ORDER.index(current)
        if idx >= len(_STAGE_ORDER) - 1:
            return ActivationTransition(
                allowed=False,
                next_stage=None,
                requirements=(),
                rollback_point=current.value,
            )
        nxt = _STAGE_ORDER[idx + 1]
        reqs: list[StageRequirement] = []

        if nxt == ActivationStage.CERTIFICATION:
            reqs.append(StageRequirement("config_valid", config_ok, "startup config"))
            reqs.append(StageRequirement("operator_signoff", operator_signoff, "operator approval"))
        elif nxt == ActivationStage.SHADOW_TRAFFIC:
            reqs.append(StageRequirement("certified", certified, "CERTIFIED state"))
        elif nxt in (
            ActivationStage.LIMITED_PUBLIC,
            ActivationStage.CONTROLLED_EXPANSION,
            ActivationStage.GENERAL_AVAILABILITY,
        ):
            reqs.append(StageRequirement("certified", certified, "certification"))
            reqs.append(StageRequirement("confidence", go_live_confidence >= 0.75, f"{go_live_confidence:.2f}"))
            reqs.append(StageRequirement("slo_ok", slo_ok, "SLO compliance"))
            reqs.append(StageRequirement("operator_signoff", operator_signoff, "sign-off"))

        allowed = all(r.passed for r in reqs)
        return ActivationTransition(
            allowed=allowed,
            next_stage=nxt if allowed else None,
            requirements=tuple(reqs),
            rollback_point=current.value,
        )

    def advance(
        self,
        *,
        operator_id: str,
        snapshot: dict[str, Any],
        certified: bool = False,
        go_live_confidence: float = 0.0,
        slo_ok: bool = True,
    ) -> ActivationTransition:
        trans = self.evaluate_next(
            certified=certified,
            go_live_confidence=go_live_confidence,
            slo_ok=slo_ok,
            operator_signoff=True,
            config_ok=True,
        )
        if not trans.allowed or trans.next_stage is None:
            return trans
        prev = self.current_stage()
        self.repository.set_activation(
            stage=trans.next_stage.value,
            previous=prev.value,
            operator_signoff=operator_id,
            snapshot=snapshot,
            rollback_point=trans.rollback_point,
        )
        logger.info(
            "event=activation_advance from=%s to=%s operator=%s",
            prev.value,
            trans.next_stage.value,
            operator_id,
        )
        return trans

    def rollback(self, *, operator_id: str, reason: str) -> ActivationStage:
        prev = self.current_stage()
        target = ActivationStage.SHADOW_TRAFFIC
        if prev in (ActivationStage.PRECHECK, ActivationStage.CERTIFICATION):
            target = ActivationStage.PRECHECK
        self.repository.set_activation(
            stage=target.value,
            previous=prev.value,
            operator_signoff=operator_id,
            snapshot={"rollback_reason": reason},
            rollback_point=prev.value,
        )
        logger.warning("event=activation_rollback to=%s reason=%s", target.value, reason)
        return target

    def rollout_stage_for_current(self) -> str:
        return _ROLLOUT_MAP.get(self.current_stage(), "INTERNAL_SHADOW")

    def status_text(
        self,
        *,
        transition: ActivationTransition | None = None,
    ) -> str:
        stage = self.current_stage()
        lines = [
            f"<b>Activation</b> · <code>{stage.value}</code>",
            f"Rollout map: <code>{self.rollout_stage_for_current()}</code>",
        ]
        if transition:
            if transition.next_stage:
                lines.append(f"Next: {transition.next_stage.value} ({'ready' if transition.allowed else 'blocked'})")
            for r in transition.requirements:
                mark = "✓" if r.passed else "✗"
                lines.append(f"{mark} {r.check_id}")
        return "\n".join(lines)
