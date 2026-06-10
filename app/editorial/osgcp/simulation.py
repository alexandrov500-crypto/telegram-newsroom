"""24h editorial feed simulation — high / low / mixed volatility scenarios."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.editorial.osgcp.arbitration_engine import arbitrate_editorial_decision
from app.editorial.osgcp.state_machine import EditorialStateKind, resolve_editorial_state


class SimulationScenario(str, Enum):
    HIGH_SIGNAL = "high_signal_day"
    LOW_SIGNAL = "low_signal_day"
    MIXED_VOLATILITY = "mixed_volatility_day"


@dataclass(frozen=True)
class SimulationTick:
    hour: int
    gravity: float
    pg: float
    gap_minutes: float
    state: str
    action: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "hour": self.hour,
            "gravity": self.gravity,
            "pg": self.pg,
            "gap_minutes": self.gap_minutes,
            "state": self.state,
            "action": self.action,
        }


@dataclass(frozen=True)
class SimulationReport:
    scenario: str
    expected_posts_per_day: int
    gap_max_minutes: float
    gap_p99_minutes: float
    substitution_avg: float
    gravity_avg: float
    ticks: tuple[SimulationTick, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario,
            "expected_posts_per_day": self.expected_posts_per_day,
            "gap_max_minutes": round(self.gap_max_minutes, 1),
            "gap_p99_minutes": round(self.gap_p99_minutes, 1),
            "substitution_avg": round(self.substitution_avg, 2),
            "gravity_avg": round(self.gravity_avg, 2),
            "tick_count": len(self.ticks),
            "ticks_sample": [t.to_dict() for t in self.ticks[:8]],
        }


def _scenario_profile(scenario: SimulationScenario, hour: int) -> tuple[float, float]:
    if scenario == SimulationScenario.HIGH_SIGNAL:
        return 78.0 + (hour % 4) * 3, 75.0 + (hour % 3) * 4
    if scenario == SimulationScenario.LOW_SIGNAL:
        return 42.0 + (hour % 5), 48.0 + (hour % 4) * 2
    if hour % 3 == 0:
        return 82.0, 80.0
    if hour % 3 == 1:
        return 45.0, 50.0
    return 62.0, 65.0


def run_24h_simulation(scenario: SimulationScenario = SimulationScenario.MIXED_VOLATILITY) -> SimulationReport:
    ticks: list[SimulationTick] = []
    gaps: list[float] = []
    gravities: list[float] = []
    subs: list[float] = []
    posts = 0
    last_post_hour = -999

    for hour in range(24):
        grav, pg = _scenario_profile(scenario, hour)
        gap = max(0.0, (hour - last_post_hour) * 60.0) if last_post_hour >= 0 else 0.0
        gaps.append(gap)

        state = resolve_editorial_state(
            gravity_avg=grav,
            gap_minutes=gap,
            desk_rejects_consecutive=0 if scenario != SimulationScenario.LOW_SIGNAL else (1 if hour > 18 else 0),
        )
        decision = arbitrate_editorial_decision(
            editorial_state=state.current_state,
            pg_total=pg,
            gravity_total=grav,
            crs_total=pg * 0.9,
            continuity_score=0.85 if gap < 90 else 0.4,
            source_independence=0.75,
            gap_minutes=gap,
        )

        if decision.action.value in {"publish", "priority_boost", "digest", "synthesize"} and not decision.reject:
            posts += 1
            last_post_hour = hour
            gravities.append(grav)
            subs.append(pg * 0.85)

        ticks.append(
            SimulationTick(
                hour=hour,
                gravity=grav,
                pg=pg,
                gap_minutes=gap,
                state=state.current_state.value,
                action=decision.action.value,
            )
        )

    sorted_gaps = sorted(gaps)
    p99_idx = min(len(sorted_gaps) - 1, int(len(sorted_gaps) * 0.99))

    return SimulationReport(
        scenario=scenario.value,
        expected_posts_per_day=posts,
        gap_max_minutes=max(gaps) if gaps else 0.0,
        gap_p99_minutes=sorted_gaps[p99_idx] if sorted_gaps else 0.0,
        substitution_avg=sum(subs) / len(subs) if subs else 0.0,
        gravity_avg=sum(gravities) / len(gravities) if gravities else 0.0,
        ticks=tuple(ticks),
    )


def run_all_scenarios() -> dict[str, Any]:
    return {
        s.value: run_24h_simulation(s).to_dict()
        for s in SimulationScenario
    }
