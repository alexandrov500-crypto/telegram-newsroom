"""Product Replacement Loop — Awareness → Trust → Reference → Return → Habit → Dependency."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ReplacementStage(str, Enum):
    AWARENESS = "awareness"
    TRUST = "trust"
    REFERENCE = "reference"
    RETURN = "return"
    HABIT = "habit"
    DEPENDENCY = "dependency"


_STAGE_KPI: dict[ReplacementStage, str] = {
    ReplacementStage.AWARENESS: "impressions",
    ReplacementStage.TRUST: "saves",
    ReplacementStage.REFERENCE: "forwards",
    ReplacementStage.RETURN: "dau",
    ReplacementStage.HABIT: "streak",
    ReplacementStage.DEPENDENCY: "substitution_rate",
}


@dataclass(frozen=True)
class ReplacementLoopState:
    stage: ReplacementStage
    kpi: str
    mechanic: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage.value,
            "kpi": self.kpi,
            "mechanic": self.mechanic,
        }


def classify_replacement_stage(
    *,
    pg_total: float,
    reference_forward_score: float,
    substitution_score: float,
    is_digest: bool = False,
    is_flagship: bool = False,
    publishing_mode: str = "core",
) -> ReplacementLoopState:
    if substitution_score >= 75 and pg_total >= 70:
        stage = ReplacementStage.DEPENDENCY
        mechanic = "replaces_external_feeds"
    elif is_digest or publishing_mode in {"elastic_fill", "editorial_synthesis"}:
        stage = ReplacementStage.HABIT
        mechanic = "daily_rhythm_digest"
    elif reference_forward_score >= 70:
        stage = ReplacementStage.REFERENCE
        mechanic = "reference_forward_to_colleague"
    elif pg_total >= 78:
        stage = ReplacementStage.RETURN
        mechanic = "open_loop_return"
    elif pg_total >= 65:
        stage = ReplacementStage.TRUST
        mechanic = "save_and_understand"
    elif is_flagship:
        stage = ReplacementStage.AWARENESS
        mechanic = "flagship_discovery"
    else:
        stage = ReplacementStage.TRUST
        mechanic = "clarity_builds_trust"

    return ReplacementLoopState(
        stage=stage,
        kpi=_STAGE_KPI[stage],
        mechanic=mechanic,
    )
