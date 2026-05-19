from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from bot.go_live.repository import GoLiveRepository

logger = logging.getLogger(__name__)


class PublicationStage(str, Enum):
    INTERNAL_SHADOW = "INTERNAL_SHADOW"
    SHADOW_TRAFFIC = "SHADOW_TRAFFIC"
    LIMITED_PUBLIC = "LIMITED_PUBLIC"
    FIRST_REAL_PUBLICATION = "FIRST_REAL_PUBLICATION"
    CONTROLLED_RAMP = "CONTROLLED_RAMP"
    GENERAL_AVAILABILITY = "GENERAL_AVAILABILITY"


_STAGE_ORDER = list(PublicationStage)

_ROLLOUT_MAP = {
    PublicationStage.INTERNAL_SHADOW: "INTERNAL_SHADOW",
    PublicationStage.SHADOW_TRAFFIC: "INTERNAL_SHADOW",
    PublicationStage.LIMITED_PUBLIC: "LIMITED_CHANNELS",
    PublicationStage.FIRST_REAL_PUBLICATION: "LOW_FREQUENCY_PUBLIC",
    PublicationStage.CONTROLLED_RAMP: "LOW_FREQUENCY_PUBLIC",
    PublicationStage.GENERAL_AVAILABILITY: "NORMAL_PRODUCTION",
}

_RELIABILITY_MAP = {
    PublicationStage.INTERNAL_SHADOW: "SHADOW",
    PublicationStage.SHADOW_TRAFFIC: "SHADOW",
    PublicationStage.LIMITED_PUBLIC: "SHADOW",
    PublicationStage.FIRST_REAL_PUBLICATION: "LIMITED_PRODUCTION",
    PublicationStage.CONTROLLED_RAMP: "LIMITED_PRODUCTION",
    PublicationStage.GENERAL_AVAILABILITY: "FULL_PRODUCTION",
}


@dataclass(frozen=True)
class StageGate:
    check_id: str
    passed: bool
    detail: str


@dataclass
class FirstPublicationWorkflow:
    """Controlled first-publication ramp with operator sign-off."""

    repository: GoLiveRepository

    def current(self) -> PublicationStage:
        row = self.repository.get_state()
        if not row:
            return PublicationStage.INTERNAL_SHADOW
        try:
            return PublicationStage(row["publication_stage"])
        except ValueError:
            return PublicationStage.INTERNAL_SHADOW

    def rollout_for(self, stage: PublicationStage | None = None) -> str:
        return _ROLLOUT_MAP.get(stage or self.current(), "INTERNAL_SHADOW")

    def reliability_mode_for(self, stage: PublicationStage | None = None) -> str:
        return _RELIABILITY_MAP.get(stage or self.current(), "SHADOW")

    def evaluate_advance(
        self,
        *,
        ga_ready: bool = False,
        certified: bool = False,
        confidence: float = 0.0,
        slo_ok: bool = True,
        operator_signoff: bool = False,
    ) -> tuple[bool, PublicationStage | None, list[StageGate]]:
        current = self.current()
        idx = _STAGE_ORDER.index(current)
        if idx >= len(_STAGE_ORDER) - 1:
            return False, None, []
        nxt = _STAGE_ORDER[idx + 1]
        gates: list[StageGate] = [
            StageGate("operator_signoff", operator_signoff, "required"),
            StageGate("slo_ok", slo_ok, "SLO"),
        ]
        if nxt in (
            PublicationStage.LIMITED_PUBLIC,
            PublicationStage.FIRST_REAL_PUBLICATION,
            PublicationStage.CONTROLLED_RAMP,
            PublicationStage.GENERAL_AVAILABILITY,
        ):
            gates.append(StageGate("certified", certified, "ops certification"))
            gates.append(StageGate("ga_ready", ga_ready, "GA readiness"))
            gates.append(
                StageGate("confidence", confidence >= 0.75, f"{confidence:.2f}"),
            )
        allowed = all(g.passed for g in gates)
        return allowed, nxt if allowed else None, gates

    def advance(
        self,
        *,
        operator_id: str,
        snapshot: dict[str, Any],
        **signals: Any,
    ) -> tuple[PublicationStage | None, list[StageGate]]:
        allowed, nxt, gates = self.evaluate_advance(
            ga_ready=bool(signals.get("ga_ready")),
            certified=bool(signals.get("certified")),
            confidence=float(signals.get("confidence", 0)),
            slo_ok=bool(signals.get("slo_ok", True)),
            operator_signoff=True,
        )
        if not allowed or nxt is None:
            return None, gates
        self.repository.set_state(
            publication_stage=nxt.value,
            rollout_stage=self.rollout_for(nxt),
            operator_signoff=operator_id,
            snapshot=snapshot,
        )
        logger.info("event=first_publication_advance stage=%s operator=%s", nxt.value, operator_id)
        return nxt, gates

    def rollback(self, *, operator_id: str, reason: str) -> PublicationStage:
        target = PublicationStage.SHADOW_TRAFFIC
        prev = self.current()
        if prev in (PublicationStage.INTERNAL_SHADOW, PublicationStage.SHADOW_TRAFFIC):
            target = PublicationStage.INTERNAL_SHADOW
        self.repository.set_state(
            publication_stage=target.value,
            rollout_stage=self.rollout_for(target),
            operator_signoff=operator_id,
            snapshot={"rollback_reason": reason},
        )
        return target

    def status_html(
        self,
        *,
        gates: list[StageGate] | None = None,
        next_stage: PublicationStage | None = None,
    ) -> str:
        stage = self.current()
        lines = [
            f"<b>First publication</b> · <code>{stage.value}</code>",
            f"Rollout: <code>{self.rollout_for(stage)}</code>",
            f"Reliability: <code>{self.reliability_mode_for(stage)}</code>",
        ]
        if next_stage:
            lines.append(f"Next: <code>{next_stage.value}</code>")
        for g in gates or []:
            lines.append(f"{'✓' if g.passed else '✗'} {g.check_id}: {g.detail}")
        return "\n".join(lines)

    def operator_commands_for_stage(self, stage: PublicationStage | None = None) -> str:
        s = stage or self.current()
        cmds = {
            PublicationStage.INTERNAL_SHADOW: "/go_live_check · /safety_status",
            PublicationStage.SHADOW_TRAFFIC: "/go_live_certify · /activation_status",
            PublicationStage.LIMITED_PUBLIC: "/activate_next_stage · confirm shadow metrics",
            PublicationStage.FIRST_REAL_PUBLICATION: "/queues_live · approve first publish",
            PublicationStage.CONTROLLED_RAMP: "/ga_status · monitor publish rate",
            PublicationStage.GENERAL_AVAILABILITY: "/platform_health · daily digest",
        }
        return cmds.get(s, "/startup_check")
