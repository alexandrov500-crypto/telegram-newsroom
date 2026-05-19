from __future__ import annotations

from collections import Counter

from bot.editorial.flow_health.attribution import attribute_starvation_causes
from bot.editorial.flow_health.diversity import floor_diversity_allows
from bot.editorial.flow_health.relaxation import apply_relaxation_budget, effective_relaxation_scale


def test_relaxation_budget_cap() -> None:
    components = {
        "starvation": 0.12,
        "overnight": 0.05,
        "cluster_relax": 0.10,
        "quality_softening": 0.08,
    }
    b = apply_relaxation_budget(components)
    assert b["relaxation_budget_used"] <= b["relaxation_budget_max"] + 0.001
    assert b["budget_scale"] <= 1.0


def test_effective_scale_bounded() -> None:
    r = effective_relaxation_scale(
        starving=True,
        low_volume=True,
        overnight=False,
        burst=False,
    )
    assert r["relaxation_budget_used"] <= r["relaxation_budget_max"]


def test_attribution_weights_sum() -> None:
    a = attribute_starvation_causes(
        Counter({"FETCHED": 40, "CLUSTERED": 20, "PUBLISHED": 1, "DEDUPED": 5}),
        Counter({"quality_low": 3}),
    )
    weights = a.get("weights") or {}
    assert abs(sum(weights.values()) - 1.0) < 0.05
    assert a.get("dominant_cause")


def test_diversity_first_story() -> None:
    d = floor_diversity_allows("Unique geopolitical development in region X", hours=6)
    assert d.get("allowed") is True
