from __future__ import annotations

from bot.editorial.flow_health.cadence import compute_cadence_health, expected_posts_for_hour
from bot.editorial.flow_health.canary_balance import effective_canary_max_per_hour
from bot.editorial.flow_health.diversity import compute_diversity_score, publish_diversity_gate


def test_expected_posts_for_hour() -> None:
    exp = expected_posts_for_hour(10)
    assert exp["min"] <= exp["max"]
    assert exp["expected"] >= exp["min"]


def test_cadence_health_shape() -> None:
    c = compute_cadence_health()
    assert "cadence_health" in c
    assert c["cadence_band"] in ("healthy", "under_cadence", "ahead")


def test_canary_cap_boost_under_cadence() -> None:
    low = effective_canary_max_per_hour(cadence_health=0.2)
    high = effective_canary_max_per_hour(cadence_health=1.0)
    assert low["effective_cap"] >= low["base_cap"]
    assert low["effective_cap"] <= low["ceiling"]
    assert high["effective_cap"] <= high["ceiling"]


def test_diversity_unique_story() -> None:
    d = compute_diversity_score(headline="Rare diplomatic breakthrough in sector Z")
    assert d.get("publish_allowed") is True
    assert float(d.get("diversity_score", 0)) > 0.3


def test_publish_gate_disabled_respects_env(monkeypatch) -> None:
    monkeypatch.setenv("PUBLISH_DIVERSITY_GATE_ENABLED", "false")
    g = publish_diversity_gate(headline="anything")
    assert g.get("allowed") is True
