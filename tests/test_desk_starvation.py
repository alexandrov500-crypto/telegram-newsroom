from __future__ import annotations

import os

from app.editorial.desk_filter import evaluate_desk_filter
from app.editorial.desk_starvation import desk_threshold_context
from app.editorial.scoring_engine import score_story


def test_market_mid_band_passes_macro_floor_not_relevance_trap(monkeypatch):
    """Quality 37–45 + relevance 0.25 should not lose to floor at quality 30."""
    monkeypatch.setenv("DESK_MIN_QUALITY_SCORE", "45")
    monkeypatch.setenv("DESK_STARVATION_HOURS", "999")
    text = (
        "Ритейлеры заявили об обнищании россиян. Директор сети магазинов Монетка "
        "Ирина Смирнова рассказала что зарплаты россиян не растут."
    )
    escore = score_story(text=text, sources=["@cb_economics"])
    desk = evaluate_desk_filter(text, escore, sources=["@cb_economics"])
    assert desk.publish
    assert desk.reason in {
        "desk_lower_priority_allow",
        "desk_macro_market_floor",
        "desk_priority_include",
    }


def test_starvation_lowers_effective_threshold(monkeypatch):
    monkeypatch.setenv("DESK_MIN_QUALITY_SCORE", "45")
    monkeypatch.setenv("DESK_STARVATION_HOURS", "1")
    monkeypatch.setenv("DESK_STARVATION_MAX_SCORE_REDUCTION", "10")
    ctx = desk_threshold_context()
    assert ctx.publish_starvation_detected
    assert ctx.effective_min_publish_score < 45.0


def test_meme_still_rejected_under_starvation(monkeypatch):
    monkeypatch.setenv("DESK_STARVATION_HOURS", "1")
    text = "лол мем про крипту 😂🤣"
    escore = score_story(text=text, sources=["@decenter"])
    desk = evaluate_desk_filter(text, escore, sources=["@decenter"])
    assert not desk.publish
