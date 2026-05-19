from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class GaReadinessState(str, Enum):
    PRE_GA = "PRE_GA"
    GA_CANDIDATE = "GA_CANDIDATE"
    GA_READY = "GA_READY"
    GA_LOCKED = "GA_LOCKED"


@dataclass(frozen=True)
class GaReadinessResult:
    state: GaReadinessState
    score: float
    blockers: tuple[str, ...]

    def summary_text(self) -> str:
        emoji = {
            GaReadinessState.GA_READY: "✅",
            GaReadinessState.GA_CANDIDATE: "🟡",
            GaReadinessState.PRE_GA: "⛔",
            GaReadinessState.GA_LOCKED: "🔒",
        }.get(self.state, "⚪")
        lines = [
            f"<b>{emoji} GA readiness</b> · <code>{self.state.value}</code>",
            f"Score: <b>{self.score:.0%}</b>",
        ]
        for b in self.blockers[:8]:
            lines.append(f"• {b}")
        return "\n".join(lines)


@dataclass
class GaReadinessEvaluator:
    min_score: float = 0.88

    def evaluate(
        self,
        *,
        uptime_stable: bool = True,
        slo_violations: int = 0,
        critical_incidents: int = 0,
        confidence_trend: float = 0.0,
        quality_avg: float = 0.0,
        publish_integrity: float = 1.0,
        operator_responsive: bool = True,
        scaling_risk: float = 0.0,
        rollback_ready: bool = True,
        certification_state: str = "NOT_READY",
        locked: bool = False,
    ) -> GaReadinessResult:
        blockers: list[str] = []
        checks = [
            ("uptime", uptime_stable),
            ("slo", slo_violations == 0),
            ("incidents", critical_incidents == 0),
            ("confidence", confidence_trend >= 0.75),
            ("quality", quality_avg >= 0.65),
            ("integrity", publish_integrity >= 0.9),
            ("operator", operator_responsive),
            ("scaling", scaling_risk < 0.65),
            ("rollback", rollback_ready),
            ("certified", certification_state == "CERTIFIED"),
        ]
        passed = sum(1 for _, ok in checks if ok)
        score = passed / len(checks)
        for name, ok in checks:
            if not ok:
                blockers.append(name)
        if locked:
            state = GaReadinessState.GA_LOCKED
        elif score >= self.min_score and not blockers:
            state = GaReadinessState.GA_READY
        elif score >= 0.75:
            state = GaReadinessState.GA_CANDIDATE
        else:
            state = GaReadinessState.PRE_GA
        return GaReadinessResult(state=state, score=score, blockers=tuple(blockers))
