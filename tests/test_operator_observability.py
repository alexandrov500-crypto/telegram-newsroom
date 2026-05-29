from __future__ import annotations

import time

from app.editorial.intelligence.operator_observability import build_operator_observability_snapshot
from app.editorial.intelligence.trend_memory import observe_narrative_event


def test_operator_observability_snapshot_contains_required_sections(tmp_path) -> None:
    rt = str(tmp_path)
    now = time.time()
    for i in range(3):
        observe_narrative_event(
            rt,
            text="NVIDIA and AI capex momentum continue.",
            category="market",
            repost_rate=0.82,
            forward_velocity=0.79,
            open_retention=0.75,
            reaction_density=0.7,
            quoteability=0.8,
            screenshot_probability=0.76,
            engagement_longevity=0.78,
            hashtags=["#AI", "#NVIDIA"],
            now_ts=now - i * 1800,
        )
    observe_narrative_event(
        rt,
        text="Macro stress returns as bond yields rise.",
        category="macro",
        repost_rate=0.38,
        forward_velocity=0.35,
        open_retention=0.3,
        reaction_density=0.28,
        quoteability=0.31,
        screenshot_probability=0.32,
        engagement_longevity=0.35,
        hashtags=["#Rates"],
        now_ts=now - 3600,
    )
    snap = build_operator_observability_snapshot(rt)
    assert "winning_narratives" in snap
    assert "dying_narratives" in snap
    assert "emerging_narratives" in snap
    assert "time_of_day_efficiency" in snap
    assert "adaptive_recommendations" in snap
    assert "alerts" in snap
    assert 0.0 <= float(snap["newsroom_health_score"]) <= 1.0


def test_operator_observability_metrics_shape(tmp_path) -> None:
    rt = str(tmp_path)
    now = time.time()
    observe_narrative_event(
        rt,
        text="Fed and inflation narrative dominates morning agenda.",
        category="macro",
        repost_rate=0.6,
        forward_velocity=0.57,
        open_retention=0.53,
        reaction_density=0.48,
        quoteability=0.52,
        screenshot_probability=0.5,
        engagement_longevity=0.55,
        hashtags=["#Fed", "#Inflation"],
        now_ts=now,
    )
    snap = build_operator_observability_snapshot(rt)
    momentum_map = snap.get("narrative_momentum_map") or []
    assert momentum_map
    row = momentum_map[0]
    for key in (
        "momentum_score",
        "growth_velocity",
        "saturation_level",
        "fatigue_probability",
        "repost_velocity",
        "retention_strength",
        "open_loop_strength",
        "hashtag_efficiency",
        "cadence_fit",
        "signal_density",
    ):
        assert key in row
