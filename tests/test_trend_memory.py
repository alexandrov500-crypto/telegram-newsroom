from __future__ import annotations

import time

from app.editorial.intelligence.trend_memory import (
    choose_hashtags,
    cluster_snapshot,
    evaluate_narrative_strategy,
    observe_narrative_event,
)
from app.editorial.scoring_engine import score_story
from app.editorial.signal_ranking import rank_story_signal


def test_trend_memory_windows_and_snapshot(tmp_path) -> None:
    rt = str(tmp_path)
    now = time.time()
    observe_narrative_event(
        rt,
        text="Fed holds rates, inflation remains sticky.",
        category="macro",
        repost_rate=0.6,
        forward_velocity=0.62,
        open_retention=0.58,
        reaction_density=0.5,
        quoteability=0.55,
        screenshot_probability=0.57,
        engagement_longevity=0.54,
        hashtags=["#Fed", "#Inflation"],
        now_ts=now - 2 * 3600,
    )
    observe_narrative_event(
        rt,
        text="Bond yields pressure equities as Fed path reprices.",
        category="macro",
        repost_rate=0.5,
        forward_velocity=0.52,
        open_retention=0.5,
        reaction_density=0.45,
        quoteability=0.48,
        screenshot_probability=0.51,
        engagement_longevity=0.5,
        hashtags=["#Rates"],
        now_ts=now - 26 * 3600,
    )
    observe_narrative_event(
        rt,
        text="Macro desk watches inflation trend into next week.",
        category="macro",
        repost_rate=0.42,
        forward_velocity=0.44,
        open_retention=0.4,
        reaction_density=0.35,
        quoteability=0.39,
        screenshot_probability=0.41,
        engagement_longevity=0.43,
        hashtags=["#Macro"],
        now_ts=now - 72 * 3600,
    )
    snap = cluster_snapshot(rt, cluster_key="macro_stress", now=now)
    assert snap.events_24h == 1
    assert snap.events_48h == 2
    assert snap.events_7d == 3
    assert 0.0 <= snap.momentum_score <= 1.0
    assert 0.0 <= snap.fatigue_probability <= 1.0


def test_narrative_strategy_priority_multiplier(tmp_path) -> None:
    rt = str(tmp_path)
    now = time.time()
    for i in range(4):
        observe_narrative_event(
            rt,
            text="NVIDIA guides higher and AI capex keeps accelerating.",
            category="market",
            repost_rate=0.82,
            forward_velocity=0.8,
            open_retention=0.76,
            reaction_density=0.74,
            quoteability=0.8,
            screenshot_probability=0.79,
            engagement_longevity=0.77,
            hashtags=["#AI", "#NVIDIA"],
            now_ts=now - (i * 1800),
        )
    strat = evaluate_narrative_strategy(rt, text="AI momentum continues in semiconductors.", category="market")
    assert strat["cluster_key"] == "ai_boom"
    assert strat["priority_multiplier"] >= 1.0


def test_choose_hashtags_prefers_winning_tags(tmp_path) -> None:
    rt = str(tmp_path)
    for i in range(3):
        observe_narrative_event(
            rt,
            text="AI cycle extends into hyperscalers and chips.",
            category="market",
            repost_rate=0.85,
            forward_velocity=0.82,
            open_retention=0.8,
            reaction_density=0.73,
            quoteability=0.83,
            screenshot_probability=0.78,
            engagement_longevity=0.8,
            hashtags=["#AI", "#NVIDIA"],
            now_ts=time.time() - i * 600,
        )
    picked = choose_hashtags(rt, cluster_key="ai_boom", candidates=["#AI", "#NVIDIA", "#Macro"], limit=2)
    assert len(picked) == 2
    assert "#AI" in picked or "#NVIDIA" in picked


def test_signal_ranking_enriches_trend_fields(tmp_path) -> None:
    rt = str(tmp_path)
    text = "Fed signals higher-for-longer rates while inflation risks persist."
    escore = score_story(text=text, sources=["@cb_economics"])
    signal = rank_story_signal(text, escore, sources=["@cb_economics"], runtime_dir=rt, category="macro")
    assert signal.narrative_cluster == "macro_stress"
    assert 0.0 <= signal.momentum_score <= 1.0
    assert 0.82 <= signal.priority_multiplier <= 1.22


def test_infer_narrative_cluster_no_false_ai_on_russian_companii() -> None:
    from app.editorial.intelligence.trend_memory import infer_narrative_cluster

    text = (
        "Сбер не видит проблем у РЖД с обслуживанием долга почти на 3,5 трлн рублей. "
        "В банке говорят, что угрозы для обязательств компании нет."
    )
    assert infer_narrative_cluster(text, category="macro") != "ai_boom"
