from __future__ import annotations

from app.editorial.content_quality import (
    has_hidden_advertising,
    is_generic_insight,
    is_incomplete_teaser,
    is_publishably_informative,
    passes_premium_newsroom_policy,
    strip_generic_why_it_matters,
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


def test_hidden_advertising_premium_channel_funnel():
    """Native ad: news teaser redirecting to undisclosed premium channel."""
    text = (
        "Strategy внесли 411.5 BTC на Coinbase Prime — на Polymarket вероятность продажи "
        "до 31 декабря 2026 года достигла 84%. Ранее Сейлор дал понять, что компания "
        "будет продавать монеты время от… Полный разбор — в premium-канале. "
        "Почему это важно: Крипторынок реагирует на ликвидность быстрее традиционных активов."
    )
    assert has_hidden_advertising(text)


def test_hidden_advertising_paywall_teaser_after_ellipsis():
    text = "Компания объявила о сделке… Подробности — в закрытом канале для подписчиков."
    assert has_hidden_advertising(text)


def test_clean_market_news_not_hidden_ad():
    text = (
        "Strategy перевела 411.5 BTC на Coinbase Prime. Аналитики Polymarket оценивают "
        "вероятность продажи до конца 2026 года в 84%, что усилило давление на крипторынок."
    )
    assert not has_hidden_advertising(text)


def test_generic_insight_boilerplate_detected_and_stripped():
    text = (
        "АТОР: самый дорогой тур в Россию купили американские туристы. "
        "Его стоимость составила $15 тысяч.\n\n"
        "Почему это важно: Событие может сдвинуть краткосрочные ожидания участников рынка."
    )
    assert is_generic_insight("Событие может сдвинуть краткосрочные ожидания участников рынка.")
    cleaned = strip_generic_why_it_matters(text)
    assert "Почему это важно" not in cleaned
    assert "$15 тысяч" in cleaned


def test_specific_insight_not_stripped():
    why = "Изменение ставки перестраивает стоимость капитала и волатильность активов."
    text = f"ФРС сигнализирует о снижении ключевой ставки.\n\nПочему это важно: {why}"
    assert not is_generic_insight(why)
    assert why in strip_generic_why_it_matters(text)
