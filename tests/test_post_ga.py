from __future__ import annotations

from pathlib import Path

import pytest

from bot.post_ga.calibration.traffic import LiveTrafficCalibrator
from bot.post_ga.optimization.proposals import SafeSelfOptimizer
from bot.post_ga.quality.learning import ProductionQualityLearner
from bot.post_ga.repository import PostGaRepository
from bot.post_ga.risk.prediction import LiveRiskPredictor
from bot.post_ga.stability.autonomy import AutonomyStabilizer
from bot.storage.db import init_database


@pytest.fixture
def repo(tmp_path: Path) -> PostGaRepository:
    init_database(tmp_path / "post_ga.db")
    return PostGaRepository(tmp_path / "post_ga.db")


def test_calibration_low_engagement(repo: PostGaRepository) -> None:
    cal = LiveTrafficCalibrator(repo)
    for _ in range(10):
        cal.record_publish(engagement=0.2)
    r = cal.calibrate()
    assert r["audience_responsiveness"] < 0.35
    assert r["pacing"]["low_engagement_suppress"] is True


def test_quality_repetitive_headline(repo: PostGaRepository) -> None:
    q = ProductionQualityLearner(repo)
    for _ in range(8):
        q.observe_output(headline="Breaking news today", summary="word " * 25, quality_overall=0.7)
    with repo._conn() as conn:
        n = conn.execute(
            "SELECT COUNT(*) FROM ops_post_ga_quality_learning WHERE pattern_type = ?",
            ("repetitive_headline",),
        ).fetchone()
    assert n is not None and int(n[0]) >= 1


def test_autonomy_fatigue_on_retries(repo: PostGaRepository) -> None:
    s = AutonomyStabilizer(repo)
    for _ in range(10):
        s.observe(queue_depth=100, retry_count=40)
    r = s.observe(queue_depth=500, retry_count=50)
    assert r["runtime_fatigue_index"] > 0.3


def test_risk_forecast_overload(repo: PostGaRepository) -> None:
    p = LiveRiskPredictor(repo)
    fc = p.forecast(queue_depth=700, queue_growth=100)
    assert fc["risks"]["overload"] > 0.5


def test_optimizer_proposal(repo: PostGaRepository) -> None:
    opt = SafeSelfOptimizer(repo, auto_threshold=0.05)
    prop = opt.propose(
        category="pacing",
        change={"factor": 0.7},
        explain="test",
        impact_magnitude=0.1,
    )
    assert prop is not None
    assert len(repo.pending_proposals()) == 1
