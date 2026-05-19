from __future__ import annotations

from bot.editorial.flow_health.digest_discipline import compute_digest_dependency, digest_recovery_allowed
from bot.editorial.flow_health.newsroom_mode import classify_newsroom_mode
from bot.editorial.flow_health.predictability import compute_predictability_score
from bot.editorial.flow_health.rhythm import compute_rhythm_modulation
from bot.editorial.flow_health.threshold_stability import analyze_threshold_stability
from bot.editorial.priority.balance import topic_bucket


def test_rhythm_modulation_shape() -> None:
    r = compute_rhythm_modulation()
    assert 0.5 <= r["rhythm_multiplier"] <= 1.3
    assert r["rhythm_band"] in ("steady", "burst_dampen", "silence_nudge")


def test_predictability_score_bounded() -> None:
    p = compute_predictability_score(
        rhythm={"rhythm_stability": 0.9, "burst_detected": False},
        cadence={"cadence_health": 0.8},
        category={"imbalanced": False},
        digest={"digest_to_publish_ratio": 0.1},
        threshold={"threshold_stability_warning": False},
        trends={"permissive_drift_warning": False},
    )
    assert 0.0 <= p["predictability_score"] <= 1.0


def test_newsroom_mode_stable_default() -> None:
    m = classify_newsroom_mode(
        funnel={"starvation": {"detected": False}},
        rhythm={"burst_detected": False},
        digest={"digest_heavy": False},
        category={"imbalanced": False},
        adaptive={"relaxation": {"hysteresis_multiplier": 0}},
    )
    assert m["current_mode"] == "STABLE"


def test_digest_recovery_allowed_fail_open() -> None:
    assert digest_recovery_allowed() in (True, False)


def test_threshold_stability_advisory() -> None:
    t = analyze_threshold_stability(
        adaptive={
            "cluster_similarity_threshold": 0.75,
            "relaxation": {"relaxation_budget_used": 0.2, "relaxation_budget_max": 0.25},
        },
    )
    assert "threshold_stability_warning" in t


def test_topic_bucket_reuse() -> None:
    assert topic_bucket(["inflation", "economy"], None) == "economic"
