from __future__ import annotations

from bot.editorial.flow_health.longtail import classify_longtail, longtail_coverage_adjustment
from bot.editorial.flow_health.novelty_pressure import compute_novelty_pressure
from bot.editorial.flow_health.realism import compute_operational_realism_index
from bot.editorial.flow_health.responsiveness import compute_medium_cycle_responsiveness
from bot.editorial.flow_health.stagnation import detect_stagnation_risk
from bot.editorial.flow_health.vitality import compute_editorial_vitality


def test_vitality_score_bounded() -> None:
    v = compute_editorial_vitality()
    assert 0.0 <= v["editorial_vitality_score"] <= 1.0
    assert v["vitality_band"] in ("healthy", "muted", "stale")


def test_stagnation_risk_levels() -> None:
    s = detect_stagnation_risk(
        vitality={"editorial_vitality_score": 0.4},
        cadence={"cadence_health": 0.95},
        category={"dominant_ratio": 0.7},
        novelty={"novelty_pressure_score": 0.65},
    )
    assert s["stagnation_risk"] in ("LOW", "MODERATE", "HIGH")


def test_novelty_pressure_shape() -> None:
    n = compute_novelty_pressure()
    assert "novelty_pressure_score" in n


def test_realism_index() -> None:
    r = compute_operational_realism_index(
        vitality={"editorial_vitality_score": 0.7},
        stagnation={"stagnation_risk": "LOW"},
        novelty={"novelty_pressure_score": 0.3},
        responsiveness={"medium_cycle_active": False},
        longtail={"longtail_share": 0.1},
        cadence={"cadence_health": 0.8},
        coverage={"coverage_score": 0.6, "distinct_story_clusters": 3},
    )
    assert r["operational_realism_band"] in ("HIGH", "MODERATE", "LOW")


def test_longtail_classification() -> None:
    assert classify_longtail(["climate", "emission"]) == "climate"


def test_responsiveness_shape() -> None:
    resp = compute_medium_cycle_responsiveness()
    assert "medium_cycle_active" in resp


def test_longtail_adjustment_fail_open() -> None:
    assert longtail_coverage_adjustment(["general"]) >= 0.0
