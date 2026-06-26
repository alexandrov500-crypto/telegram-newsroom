"""Unified wire post format — complete thoughts, cb_economics-class shape."""

from __future__ import annotations

import pytest

from app.editorial.subscriber_wire_format import build_subscriber_wire_parts
from app.editorial.wire_post_format import ensure_complete_ending, normalize_wire_body


@pytest.fixture(autouse=True)
def _wire_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WIRE_POST_BODY_MAX_CHARS", "1050")
    monkeypatch.setenv("WIRE_POST_MIN_BODY_CHARS", "280")
    monkeypatch.setenv("WIRE_POST_INTEGRATED_CLOSURE", "true")
    monkeypatch.setenv("NEWSROOM_PUBLISH_FORMAT", "subscriber_wire")


def test_ensure_complete_ending_fixes_dangling_conjunction() -> None:
    out = ensure_complete_ending("ЦБ сохранил ставку, потому что")
    assert out.endswith(".")
    assert "потому что" not in out


def test_normalize_wire_body_keeps_multiple_sentences() -> None:
    body = (
        "ЦБ сохранил ключевую ставку на уровне 16%. "
        "Совет директоров отметил замедление инфляции до 5,2% г/г. "
        "Рынки ожидают смягчения политики на следующем заседании. "
        "Инвесторы пересматривают доходности ОФЗ на горизонте года."
    )
    out = normalize_wire_body(body)
    assert len(out) >= 200
    assert out.count(".") >= 3
    assert out.endswith(".")
    assert "…" not in out


def test_subscriber_wire_no_takeaway_strip_with_integrated_closure() -> None:
    raw = (
        "ЦБ сохранил ключевую ставку на 16%.\n\n"
        "Совет директоров учёл замедление инфляции до 5,2%. "
        "Рынки ожидают следующего заседания в июле. "
        "Это снизит давление на рублёвые активы в ближайшие недели."
    )
    parts = build_subscriber_wire_parts(raw, growth_meta={"virality_score": 80})
    assert parts.takeaway == ""
    assert "снизит давление" in parts.body.lower()
    assert parts.body.endswith(".")
