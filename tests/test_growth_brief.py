from __future__ import annotations

import pytest

from app.editorial.public_format import format_public_story
from app.growth_layer.format.growth_brief import (
    blocks_from_plain_text,
    compose_growth_brief,
    render_growth_brief_html,
)
from app.growth_layer.format.profiles import publish_format_mode, resolve_format_profile


@pytest.fixture(autouse=True)
def _cb_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSROOM_CB_BRIEF_FORMAT", "true")
    monkeypatch.setenv("W3_EDITORIAL_PIPELINE_ENABLED", "false")
    monkeypatch.setenv("HEADLINE_ENGINE_ENABLED", "false")


def test_compose_growth_brief_four_blocks() -> None:
    blocks = blocks_from_plain_text(
        "ЦБ повысил ставку на 50 б.п.",
        "Регулятор ускорил борьбу с инфляцией. Рынок облигаций отреагировал ростом доходности. "
        "Для заёмщиков кредиты подорожают. Базовый сценарий — дальнейшее ужесточение.",
    )
    body = compose_growth_brief(blocks)
    assert "⚡ Что произошло" in body
    assert "📊 Почему это важно" in body
    assert "💰 Что это значит для денег" in body
    assert "🎯 Что будет дальше" in body


def test_render_growth_brief_html() -> None:
    blocks = blocks_from_plain_text("Заголовок", "Текст новости с выводом.")
    html = render_growth_brief_html(blocks)
    assert "<b>" in html
    assert "⚡ Что произошло" in html


def test_hybrid_format_profile_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSROOM_PUBLISH_FORMAT", "hybrid")
    assert resolve_format_profile(40) == "cb_brief"
    assert resolve_format_profile(71) == "growth_brief"
    assert resolve_format_profile(90) == "growth_brief"


def test_hybrid_uses_growth_brief_at_publish(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSROOM_PUBLISH_FORMAT", "hybrid")
    growth_meta = {"virality_score": 78, "virality_tier": "viral_candidate", "format_profile": "growth_brief"}
    story = format_public_story(
        "ЦБ повысил ставку",
        "Регулятор ускорил борьбу с инфляцией. Рынок облигаций отреагировал.",
        growth_meta=growth_meta,
    )
    assert "⚡ Что произошло" in story.summary


def test_cb_brief_unaffected_when_standard(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSROOM_PUBLISH_FORMAT", "hybrid")
    growth_meta = {"virality_score": 32, "format_profile": "cb_brief"}
    story = format_public_story(
        "ЦБ повысил ключевую ставку на 50 б.п.",
        "Решение поддерживает рубль и сдерживает инфляцию.",
        growth_meta=growth_meta,
    )
    assert "⚡ Что произошло" not in story.summary
    assert story.headline.startswith("ЦБ")


def test_default_publish_format_is_cb_brief(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSROOM_CHANNEL_BEAT", "off")
    monkeypatch.setenv("NEWSROOM_PUBLISH_FORMAT", "cb_brief")
    assert publish_format_mode() == "cb_brief"
