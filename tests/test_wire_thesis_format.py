"""Wire thesis format — scrub boilerplate, RBC TV digest, thesis bullets."""

from __future__ import annotations

import pytest

from app.editorial.clean_channel_copy import scrub_editorial_pipeline_filler
from app.editorial.subscriber_wire_format import build_subscriber_wire_parts, render_subscriber_wire_html
from app.editorial.wire_post_format import normalize_wire_body, strip_wire_pipeline_boilerplate
from app.editorial.wire_source_normalize import normalize_rbc_tv_roundup, normalize_wire_source_text


@pytest.fixture(autouse=True)
def _wire_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSROOM_CHANNEL_BEAT", "top_news")
    monkeypatch.setenv("WIRE_POST_THESIS_BULLETS", "true")
    monkeypatch.setenv("EDITORIAL_AUDIENCE_UNIFICATION_LAYER", "false")


def test_strip_auh_boilerplate() -> None:
    raw = (
        "Индекс Мосбиржи падает 16 недель подряд — это новый рекорд. "
        "Индекс RGBI ушёл ниже 116 пунктов. "
        "ключевое изменение фиксируется несколькими источниками. "
        "Почему важно: это влияет на решения инвесторов, компаний и политиков. "
        "Связь с макроэкономикой: событие влияет на глобальный контекст решений."
    )
    out = strip_wire_pipeline_boilerplate(raw)
    assert "Почему важно" not in out
    assert "Связь с макро" not in out
    assert "16 недель" in out


def test_normalize_rbc_tv_roundup() -> None:
    raw = (
        "Главные новости — в утреннем выпуске на телеканале РБК: "
        "▪ 00:00-01:29 — Митинг против соглашения Ливана и Израиля. "
        "▪01:30-03:23 — США ударили по целям в Иране."
    )
    out = normalize_rbc_tv_roundup(raw)
    assert out is not None
    assert "00:00" not in out
    assert "утреннем выпуске" not in out.lower()
    assert "▸" in out
    assert "Иране" in out


def test_thesis_body_from_sentences() -> None:
    body = (
        "Индекс Мосбиржи падает 16 недель подряд — это новый рекорд. "
        "Индекс гособлигаций RGBI ушёл ниже 116 пунктов. "
        "Инвесторы сокращали риск сразу в акциях и длинных ОФЗ."
    )
    out = normalize_wire_body(body)
    assert out.count("▸") >= 2
    assert "Почему важно" not in out


def test_render_no_share_nudge(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHANNEL_PRODUCT_SHARE_NUDGE", "true")
    raw = (
        "Индекс Мосбиржи падает 16 недель подряд.\n\n"
        "RGBI опустился ниже 116 пунктов. Рынок сокращает риск по всем классам активов."
    )
    html = render_subscriber_wire_html(raw, '[{"channel": "@cb_economics"}]', growth_meta={"virality_score": 90})
    assert "Перешлите" not in html
    assert "Почему важно" not in html


def test_scrub_removes_duplicate_headline_leadin() -> None:
    raw = (
        "Индекс Мосбиржи падает 16 недель подряд - это новый рекорд.\n\n"
        "Индекс Мосбиржи падает 16 недель подряд - это новый рекорд. "
        "RGBI опустился ниже 116 пунктов."
    )
    cleaned = scrub_editorial_pipeline_filler(raw)
    parts = build_subscriber_wire_parts(cleaned)
    assert parts.headline
    assert parts.body.count("16 недель") <= 2
    assert normalize_wire_source_text(raw).count("16 недель") >= 1
