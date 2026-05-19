from __future__ import annotations

import asyncio
from pathlib import Path

from bot.week1.alerts.noise_reduction import AlertNoiseReducer
from bot.week1.baseline.capture import ProductionBaselineCapture
from bot.week1.factory import build_week1_stack
from bot.week1.repository import Week1Repository
from bot.week1.risk.stabilization import RiskStabilization
from bot.week1.survivability.scoring import SurvivabilityScoring
from bot.storage.db import init_database


def test_alert_dedupe(tmp_path: Path) -> None:
    init_database(tmp_path / "w1.db")
    repo = Week1Repository(tmp_path / "w1.db")
    reducer = AlertNoiseReducer(repo, dedupe_sec=3600)
    v1 = reducer.evaluate(title="queue high", severity="warning", symptoms=["backlog"])
    v2 = reducer.evaluate(title="queue high", severity="warning", symptoms=["backlog"])
    assert v1.surface
    assert not v2.surface


def test_baseline_capture(tmp_path: Path) -> None:
    init_database(tmp_path / "w2.db")
    repo = Week1Repository(tmp_path / "w2.db")
    cap = ProductionBaselineCapture(repo)
    snaps = cap.capture_all({"queue_depth": 50, "quality_avg": 0.85})
    assert "quality" in snaps
    assert repo.get_state()["baseline_captured"] == 1


def test_stabilization_risk_high() -> None:
    risk = RiskStabilization(Week1Repository(Path(":memory:")))
    s = risk.score({"quality_avg": 0.5, "open_incidents": 3, "queue_depth": 300})
    assert s["stabilization_risk"] > 0.4


def test_survivability(tmp_path: Path) -> None:
    init_database(tmp_path / "w3.db")
    surv = SurvivabilityScoring(Week1Repository(tmp_path / "w3.db"))
    out = surv.compute({"quality_avg": 0.9, "uptime_score": 0.99, "queue_depth": 20})
    assert out["survivability_score"] > 0.7


def test_coordinator_tick(tmp_path: Path) -> None:
    async def _run() -> None:
        init_database(tmp_path / "w4.db")
        coord = build_week1_stack(tmp_path / "w4.db")
        await coord.startup()
        t = await coord.tick({"quality_avg": 0.88, "queue_depth": 40})
        assert "survivability_score" in t

    asyncio.run(_run())
