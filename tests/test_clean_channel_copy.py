"""Tests for clean cb_economics-style publish copy."""

from __future__ import annotations

import pytest

from app.editorial.clean_channel_copy import (
    prepare_clean_channel_post,
    scrub_editorial_pipeline_filler,
)


@pytest.fixture(autouse=True)
def _enable_clean_copy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSROOM_CLEAN_CHANNEL_COPY", "true")
    monkeypatch.setenv("NEWSROOM_CB_BRIEF_FORMAT", "true")
    monkeypatch.setenv("NEWSROOM_CHANNEL_BEAT", "top_news")
    monkeypatch.setenv("NEWSROOM_REFERENCE_MODEL", "cb_economics")


def test_scrub_removes_pipeline_boilerplate() -> None:
    raw = (
        "Золото стало крупнейшим резервным активом.\n\n"
        "Почему это важно: событие меняет контекст для рынков и решений.\n\n"
        "Что дальше: следим за подтверждением и реакцией участников.\n\n"
        "Геополитический контекст усиливает неопределённость для бизнеса.\n\n"
        "#GeoShift #MarketShock"
    )
    out = scrub_editorial_pipeline_filler(raw)
    assert "Почему это важно" not in out
    assert "Что дальше" not in out
    assert "#GeoShift" not in out
    assert "Золото" in out


def test_scrub_removes_source_channel_chrome() -> None:
    raw = (
        "Золото стало крупнейшим резервным активом.\n\n"
        "▶️На конец 2025 года золото составило 27% резервов.\n\n"
        "◻️◻️◻️\n\n"
        "Почему это важно: событие меняет контекст для рынков и решений."
    )
    out = scrub_editorial_pipeline_filler(raw)
    assert "▶️" not in out
    assert "◻" not in out
    assert "\n\n" in out
    assert "27%" in out


def test_prepare_clean_channel_post_has_headline_and_body() -> None:
    raw = (
        "ЦБ сохранил ключевую ставку на текущем уровне.\n\n"
        "Решение совета директоров учитывает замедление инфляции. "
        "Рынки ожидают следующего заседания в июле."
    )
    out = prepare_clean_channel_post(raw)
    assert "\n\n" in out
    assert out.endswith(".")
    assert "Почему это важно" not in out
