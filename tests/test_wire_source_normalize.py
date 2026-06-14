"""Tests for wire source normalization and refusal recovery prompts."""

from __future__ import annotations

import pytest

from ai.editorial import build_refusal_recovery_system_prompt
from ai.fallback_summarizer import fallback_summarize_cluster
from app.editorial.wire_source_normalize import dedupe_headline_in_paragraph, normalize_wire_source_text
from tests.conftest import minimal_test_settings


def test_dedupe_rbc_headline_repeat() -> None:
    raw = (
        "Сборная Австралии победила Турцию на чемпионате мира по футболу "
        "Сборная Австралии со счетом 2:0 победила команду Турции в матче первого тура."
    )
    out = dedupe_headline_in_paragraph(raw)
    assert out.count("Сборная Австралии") >= 1
    assert "\n\n" in out


def test_strip_banksta_labels() -> None:
    raw = (
        "Дональд Трамп согласился разморозить активы.\n\n"
        "Что происходит: ключевое изменение фиксируется источниками.\n\n"
        "Почему важно: это влияет на рынок."
    )
    out = normalize_wire_source_text(raw)
    assert "Что происходит" not in out
    assert "Почему важно" not in out
    assert "разморозить" in out


def test_fallback_single_post_wire_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    from types import SimpleNamespace

    monkeypatch.setenv("NEWSROOM_CHANNEL_BEAT", "top_news")
    monkeypatch.setenv("NEWSROOM_CLEAN_CHANNEL_COPY", "true")
    monkeypatch.setenv("NEWSROOM_PUBLISH_FORMAT", "subscriber_wire")
    post = SimpleNamespace(
        id=1,
        channel_name="@rbc_news",
        message_id=99,
        text=(
            "Аномальная жара в Москве завершается ☀Суббота станет финальным днем "
            "аномально жаркой погоды в Москве, сообщил синоптик."
        ),
    )
    sc = fallback_summarize_cluster([post], max_body_chars=1200)
    assert "☀" not in sc.post_text
    assert "\n\n" in sc.post_text
    assert "жара" in sc.post_text.lower() or "москв" in sc.post_text.lower()


def test_refusal_recovery_prompt_mentions_json() -> None:
    settings = minimal_test_settings()
    prompt = build_refusal_recovery_system_prompt(settings)
    assert "JSON" in prompt
    assert "отказ" in prompt.lower() or "отказывайся" in prompt.lower()
