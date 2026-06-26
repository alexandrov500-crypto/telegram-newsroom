"""Desk filter — wire beat macro/market-only triage."""

from __future__ import annotations

import pytest

from app.editorial.desk_filter import evaluate_desk_filter
from app.editorial.scoring_engine import score_story


@pytest.fixture(autouse=True)
def _news_beat(monkeypatch):
    monkeypatch.setenv("NEWSROOM_CHANNEL_BEAT", "top_news")
    monkeypatch.setenv("WIRE_BEAT_MACRO_MARKET_ONLY", "true")


def _decision(text: str):
    escore = score_story(text=text, sources=["@banksta"])
    return evaluate_desk_filter(text, escore, sources=["@banksta"])


def test_wire_beat_rejects_sports():
    d = _decision("Футбол: матч 2:1 в чемпионате мира завершился победой хозяев поля.")
    assert d.publish is False
    assert "wire_beat_off_topic" in d.reason


def test_wire_beat_rejects_lifestyle():
    d = _decision("Трамп отметил день рождения в кругу семьи — подробности tabloid.")
    assert d.publish is False
    assert "wire_beat_off_topic" in d.reason


def test_wire_beat_allows_macro():
    d = _decision("Росстат: инфляция в мае замедлилась до 7,4% г/г, ключевая ставка ЦБ под вопросом.")
    assert d.publish is True
    assert d.editorial_category == "macro"
