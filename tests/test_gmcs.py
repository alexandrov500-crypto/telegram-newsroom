"""Tests for GMCS — Global Multi-Channel Competitive Simulation."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.editorial.gmcs.competitive_simulator import simulate_ecosystem_competition
from app.editorial.gmcs.controller import run_gmcs_competitive_analysis
from app.editorial.gmcs.ecosystem_registry import ECOSYSTEM_COMPETITORS
from app.editorial.gmcs.market_dominance_index import compute_market_dominance
from app.editorial.gmcs.state import gmcs_snapshot, record_gmcs_evaluation


@pytest.fixture(autouse=True)
def _enable_gmcs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDITORIAL_GMCS_LAYER", "true")


def test_ecosystem_registry_has_competitors() -> None:
    assert len(ECOSYSTEM_COMPETITORS) >= 8


def test_simulate_ecosystem_high_substitution() -> None:
    sim = simulate_ecosystem_competition(
        vertical="macro",
        substitution_score=85,
        dual_audience_trust=0.7,
        imri_score=80,
        cross_domain=True,
    )
    assert sim.aggregate_win_rate >= 0.5
    assert sim.channels_substituted_estimate >= 2


def test_market_dominance_tier() -> None:
    sim = simulate_ecosystem_competition(substitution_score=90, imri_score=85, dual_audience_trust=0.75)
    dom = compute_market_dominance(sim, imri_score=85)
    assert dom.index >= 60


def test_run_gmcs_competitive_analysis() -> None:
    layers = {
        "ugsol": {"imri": {"score": 78}},
        "mpaes": {"dual_audience_trust": 0.68, "hub_substitution": {"vertical": "macro", "substitution_score": 72}},
        "product_os": {"channel_substitution": {"substitution_score": 75}},
    }
    _, extras = run_gmcs_competitive_analysis("Fed and markets cross-domain update", runtime_dir=None, layer_extras=layers)
    assert "gmcs" in extras
    assert extras["gmcs"]["market_dominance"]["index"] > 0


def test_gmcs_state(tmp_path: Path) -> None:
    record_gmcs_evaluation(str(tmp_path), mdi=76, channels_substituted=4, vertical="macro", published=True)
    snap = gmcs_snapshot(str(tmp_path))
    assert snap["published_today"] == 1
