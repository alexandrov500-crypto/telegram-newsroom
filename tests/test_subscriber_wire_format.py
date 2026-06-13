"""Tests for Subscriber Wire publish format."""

from __future__ import annotations

import pytest

from app.editorial.subscriber_wire_format import (
    build_subscriber_wire_parts,
    highlight_key_numbers_html,
    render_subscriber_wire_html,
    subscriber_wire_format_enabled,
)
from app.growth_layer.format.profiles import publish_format_mode


@pytest.fixture(autouse=True)
def _wire_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSROOM_PUBLISH_FORMAT", "subscriber_wire")
    monkeypatch.setenv("NEWSROOM_CB_BRIEF_FORMAT", "true")
    monkeypatch.setenv("NEWSROOM_CHANNEL_BEAT", "top_news")
    monkeypatch.setenv("NEWSROOM_CLEAN_CHANNEL_COPY", "true")


def test_subscriber_wire_mode_active() -> None:
    assert subscriber_wire_format_enabled()
    assert publish_format_mode() == "subscriber_wire"


def test_wire_parts_headline_and_body() -> None:
    raw = (
        "ЦБ сохранил ключевую ставку на 16%.\n\n"
        "Совет директоров учёл замедление инфляции до 5,2%. "
        "Рынки ожидают следующего заседания в июле."
    )
    parts = build_subscriber_wire_parts(raw)
    assert parts.headline.startswith("ЦБ")
    assert "16" in parts.headline
    assert "Почему это важно" not in parts.to_plain_block()


def test_number_highlight_html() -> None:
    html = highlight_key_numbers_html("Ставка выросла на 50 б.п. до 16%.")
    assert "<code>" in html
    assert "16%" in html


def test_render_no_hashtags_or_growth_blocks() -> None:
    raw = (
        "Золото обогнало казначейские облигации США.\n\n"
        "На конец 2025 года золото составило 27% резервов центробанков. "
        "Доля Treasuries снизилась с 25% до 22%."
    )
    html = render_subscriber_wire_html(raw, '[{"channel": "@cb_economics"}]')
    assert "<b>" in html
    assert "Источник:" in html
    assert "#" not in html
    assert "Что произошло" not in html
    assert "Почему это важно:" not in html


def test_breaking_prefix() -> None:
    raw = "СРОЧНО: ЦБ повысил ставку на 100 б.п.\n\nРешение вступает в силу с завтрашнего дня."
    parts = build_subscriber_wire_parts(raw)
    assert parts.breaking
    assert parts.to_plain_block().startswith("⚡")


def test_share_nudge_from_channel_product() -> None:
    raw = "Fed сохранила ставку.\n\nРынок оценивает траекторию инфляции."
    growth_meta = {
        "virality_score": 72,
        "channel_product": {
            "enable_share_nudge": True,
            "share_nudge": "Перешлите коллеге из финансов.",
        },
    }
    html = render_subscriber_wire_html(raw, "[]", growth_meta=growth_meta)
    assert "Перешлите коллеге" in html
