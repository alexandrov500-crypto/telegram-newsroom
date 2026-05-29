from __future__ import annotations

from app.editorial.content_quality import (
    has_hidden_advertising,
    is_incomplete_teaser,
    is_publishably_informative,
    passes_premium_newsroom_policy,
)
from app.editorial.public_post_formatter import format_public_post_html


def test_truncated_vedofon_style_rejected():
    text = (
        "🍿 Корейская похоронная компания вложила предоплаты клиентов в рискованный 2x ETF "
        "на акции BitMine, и получила нереализованную просадку…"
    )
    assert not is_publishably_informative(text)
    assert is_incomplete_teaser(text)


def test_complete_story_passes():
    text = (
        "Корейская похоронная компания вложила предоплаты клиентов в рискованный 2x ETF "
        "на акции BitMine. Компания зафиксировала нереализованную просадку после резкого "
        "падения котировок."
    )
    assert is_publishably_informative(text)


def test_single_long_russian_sentence_passes():
    text = (
        "Apple удалила из российского App Store 1213 приложений по требованию "
        "Роскомнадзора за 2025 год, говорится в отчёте компании."
    )
    assert not is_publishably_informative(text)


def test_strip_dangling_ellipsis_removes_trailing_colon() -> None:
    from app.editorial.content_quality import strip_dangling_ellipsis

    assert strip_dangling_ellipsis("угрозы для обязательств компании нет:…").endswith("нет")
    assert not strip_dangling_ellipsis("угрозы для обязательств компании нет:…").endswith(":")


def test_public_template_has_headline_body_and_source():
    body = (
        "Корейская компания вложила предоплаты в 2x ETF на BitMine. "
        "Регуляторы проверяют, как распоряжаются средствами клиентов."
    )
    html = format_public_post_html(body, '[{"channel": "@vedofon"}]')
    assert "<b>" in html
    assert "BitMine" in html
    assert "Источник:" in html
    assert "…" not in html


def test_premium_policy_rejects_bureaucratic_filler_without_implication():
    text = (
        "Приказом ФТС утверждена форма предписания о выезде транспортного средства с товарами "
        "за пределы территории Российской Федерации. Документ вступает в силу после публикации."
    )
    assert not passes_premium_newsroom_policy(text)


def test_premium_policy_accepts_signal_with_impact():
    text = (
        "Россия ужесточает контроль вывоза товаров через границу. "
        "ФТС утвердила новый формат предписаний, что может усилить давление на логистику и "
        "экспортные цепочки в ближайшие кварталы."
    )
    assert passes_premium_newsroom_policy(text)


def test_hidden_advertising_detected():
    text = (
        "Партнерский материал: переходите по ссылке и используйте промокод NEWS10 "
        "для скидки на подписку. https://example.com/?utm_source=telegram"
    )
    assert has_hidden_advertising(text)
