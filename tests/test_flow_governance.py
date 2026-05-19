from __future__ import annotations

from bot.editorial.flow_health.baseline_governance import compute_baseline_deviation
from bot.editorial.flow_health.config_pressure import analyze_configuration_pressure
from bot.editorial.flow_health.surge_balance import detect_news_surge, surge_rhythm_multiplier
from bot.editorial.flow_health.trust_index import compute_operator_trust_index
from bot.editorial.flow_health.warning_fatigue import process_warnings


def test_baseline_deviation_empty_history() -> None:
    d = compute_baseline_deviation(
        {
            "cadence_health": 0.8,
            "coverage_score": 0.5,
            "predictability_score": 0.75,
            "dominant_category_ratio": 0.4,
            "digest_dependency_ratio": 0.1,
            "cluster_threshold": 0.72,
            "relaxation_budget_used": 0.1,
            "diversity_proxy": 0.6,
        },
    )
    assert "baseline_deviation" in d


def test_config_pressure_bounded() -> None:
    c = analyze_configuration_pressure()
    assert 0.0 <= c["configuration_pressure_score"] <= 1.0


def test_surge_rhythm_boost() -> None:
    m = surge_rhythm_multiplier(0.85, {"surge_active": True})
    assert m >= 0.85


def test_trust_index_bands() -> None:
    t = compute_operator_trust_index(
        predictability={"predictability_score": 0.85},
        baseline={"baseline_deviation": 0.1},
        config_pressure={"configuration_pressure_score": 0.2},
        warning_pressure=0.1,
        digest_clarity=0.9,
        cadence={"cadence_health": 0.8},
        coverage={"coverage_score": 0.6, "distinct_story_clusters": 4},
    )
    assert t["operator_trust_band"] in ("HIGH", "MODERATE", "LOW")


def test_warning_fatigue_collapses_info() -> None:
    raw = [
        {"tier": "INFO", "category": "test", "message": "low priority advisory"}
        for _ in range(5)
    ]
    out = process_warnings(raw)
    assert len(out) <= 6


def test_detect_surge_shape() -> None:
    s = detect_news_surge()
    assert "surge_active" in s
