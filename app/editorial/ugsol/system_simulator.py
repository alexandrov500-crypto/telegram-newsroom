"""Full system simulation — volatility, silence, mixed signal days."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.editorial.ugsol.control_tower import resolve_final_editorial_decision
from app.editorial.ugsol.imri import compute_imri


class SimulationScenario(str, Enum):
    HIGH_VOLATILITY = "high_volatility_news_day"
    SILENT_NO_SIGNAL = "silent_no_signal_day"
    MIXED_GEO_MARKETS = "mixed_geopolitical_markets_day"


@dataclass(frozen=True)
class SimulationResult:
    scenario: SimulationScenario
    imri_trajectory: tuple[float, ...]
    continuity_stable: bool
    audience_drift: float
    fatigue_risk: float
    substitution_efficiency: float
    publish_count: int
    digest_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario.value,
            "imri_trajectory": list(self.imri_trajectory),
            "continuity_stable": self.continuity_stable,
            "audience_drift": round(self.audience_drift, 3),
            "fatigue_risk": round(self.fatigue_risk, 3),
            "substitution_efficiency": round(self.substitution_efficiency, 3),
            "publish_count": self.publish_count,
            "digest_count": self.digest_count,
        }


def _scenario_layers(scenario: SimulationScenario, slot: int) -> dict[str, Any]:
    base: dict[str, Any] = {
        "product_os": {
            "product_gravity": {"total": 65},
            "channel_substitution": {"substitution_score": 62},
            "virality_v2": {"forward_prediction": 45},
        },
        "mpaes": {
            "dual_audience_trust": 0.62,
            "primary_segment": "reference_operator_male",
            "cognitive_segmentation": {"segments": []},
            "hub_substitution": {"substitution_score": 65},
        },
        "ccd": {"experience_fit": 0.65},
        "osgcp": {
            "format_mode": "context",
            "editorial_decision": {"action": "publish", "format_mode": "context", "reject": False},
            "continuity": {"triggered": False},
            "anti_pause": {"anti_pause_active": False},
        },
    }

    if scenario == SimulationScenario.HIGH_VOLATILITY:
        base["product_os"]["product_gravity"]["total"] = 82 + (slot % 3) * 2
        base["product_os"]["channel_substitution"]["substitution_score"] = 78
        base["priority_boost"] = slot % 4 == 0
        base["osgcp"]["format_mode"] = "signal" if slot % 4 == 0 else "context"
        base["osgcp"]["editorial_decision"]["action"] = "priority_boost" if slot % 4 == 0 else "publish"
    elif scenario == SimulationScenario.SILENT_NO_SIGNAL:
        base["product_os"]["product_gravity"]["total"] = 48 + slot
        base["product_os"]["channel_substitution"]["substitution_score"] = 42
        base["osgcp"]["continuity"]["triggered"] = slot >= 2
        base["osgcp"]["anti_pause"]["anti_pause_active"] = slot >= 3
        base["osgcp"]["editorial_decision"]["action"] = "digest" if slot >= 2 else "publish"
        base["force_digest_slot"] = slot >= 2
    else:
        base["product_os"]["channel_substitution"]["substitution_score"] = 70 + (slot % 2) * 5
        base["mpaes"]["hub_substitution"]["substitution_score"] = 72
        base["ccd"]["experience_fit"] = 0.72

    return base


def run_scenario(
    scenario: SimulationScenario,
    *,
    runtime_dir: str | None = None,
    slots: int = 8,
) -> SimulationResult:
    imri_traj: list[float] = []
    publish_n = 0
    digest_n = 0
    drifts: list[float] = []
    fatigues: list[float] = []
    subs: list[float] = []
    continuity_ok = True

    for i in range(slots):
        layers = _scenario_layers(scenario, i)
        decision, meta = resolve_final_editorial_decision(
            layers,
            runtime_dir=runtime_dir,
            publishing_mode="core",
            is_breaking=bool(layers.get("priority_boost")),
        )
        imri = meta.get("imri") if isinstance(meta.get("imri"), dict) else {}
        imri_traj.append(float(imri.get("score") or 50))
        bal = meta.get("audience_balance") if isinstance(meta.get("audience_balance"), dict) else {}
        drifts.append(float(bal.get("drift") or 0))
        flow = meta.get("content_flow") if isinstance(meta.get("content_flow"), dict) else {}
        if float(flow.get("gap_minutes") or 0) >= 90:
            continuity_ok = False
        sig = layers.get("product_os") if isinstance(layers.get("product_os"), dict) else {}
        cse = sig.get("channel_substitution") if isinstance(sig.get("channel_substitution"), dict) else {}
        subs.append(float(cse.get("substitution_score") or 50) / 100.0)
        fatigues.append(max(0.0, 1.0 - float(meta.get("system_objective", {}).get("composite_score") or 0.5)))

        if decision.publish:
            publish_n += 1
        if decision.mode.value in {"digest", "synthesis"}:
            digest_n += 1

    return SimulationResult(
        scenario=scenario,
        imri_trajectory=tuple(imri_traj),
        continuity_stable=continuity_ok,
        audience_drift=sum(drifts) / len(drifts) if drifts else 0.0,
        fatigue_risk=sum(fatigues) / len(fatigues) if fatigues else 0.0,
        substitution_efficiency=sum(subs) / len(subs) if subs else 0.0,
        publish_count=publish_n,
        digest_count=digest_n,
    )


def run_all_scenarios(runtime_dir: str | None = None) -> dict[str, Any]:
    results = [run_scenario(s, runtime_dir=runtime_dir) for s in SimulationScenario]
    return {
        "scenarios": [r.to_dict() for r in results],
        "summary": {
            "all_continuity_stable": all(r.continuity_stable for r in results),
            "avg_substitution_efficiency": round(
                sum(r.substitution_efficiency for r in results) / len(results), 3
            ),
            "avg_fatigue_risk": round(sum(r.fatigue_risk for r in results) / len(results), 3),
        },
    }
