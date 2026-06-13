"""News beat wire bypass for growth intelligence gate."""

from __future__ import annotations

import os

from app.editorial.stability.growth_decision import evaluate_growth_decision


def test_news_beat_bypasses_missing_why_matters(monkeypatch) -> None:
    monkeypatch.setenv("NEWSROOM_CHANNEL_BEAT", "top_news")
    monkeypatch.setenv("AUTONOMOUS_EDITORIAL_MODE", "true")
    text = (
        "ЦБ сохранил ключевую ставку на уровне 21%. "
        "Регулятор указал на устойчивость инфляционных ожиданий и сохранение жёсткой политики."
    )
    decision = evaluate_growth_decision(
        text,
        quality_score=53.0,
        publishing_mode="core",
        editorial_category="market",
    )
    assert not decision.reject
