from __future__ import annotations

import re

from app.editorial.public_post_formatter import format_public_post_html, format_public_post_plain
from app.editorial.source_attribution import resolve_source_attribution


def test_tier2_attribution_footer() -> None:
    attr = resolve_source_attribution(["@cb_economics"])
    assert attr.tier == 2
    assert attr.footer and "Источник:" in attr.footer


def test_tier3_strips_urls_and_mandatory_footer() -> None:
    attr = resolve_source_attribution(["@random_channel_xyz"])
    assert attr.tier == 3
    assert attr.mandatory
    assert attr.strip_urls_from_body


def test_formatter_no_duplicate_source_lines() -> None:
    body = (
        "ЦБ повысил ключевую ставку на 50 б.п.\n\n"
        "Решение поддерживает рубль и сдерживает инфляцию.\n\n"
        "Источник: @cb_economics\n"
        "Источник: @cb_economics"
    )
    sources = json_sources = '[{"channel": "@cb_economics", "message_id": 1}]'
    out = format_public_post_plain(body, sources)
    assert out.count("Источник:") <= 1


def test_formatter_no_tabloid_markers() -> None:
    body = "Шокирующая сенсация: компания отчиталась о выручке."
    out = format_public_post_plain(body, "[]", include_cta=False)
    assert "шокирующ" not in out.lower()


def test_formatter_default_includes_cta() -> None:
    out = format_public_post_plain("Заголовок\n\nТекст новости.", '[{"channel": "@cb_economics"}]')
    assert "Подписывайтесь" in out


def test_formatter_adaptive_cta_for_crypto() -> None:
    out = format_public_post_plain(
        "Крипторынок оживился после запуска нового ETF на биткоин.\n\nОбъемы выросли.",
        '[{"channel": "@decenter"}]',
    )
    assert "крипторынок" in out.lower()


def test_formatter_no_signature_label_by_default() -> None:
    html = format_public_post_html(
        "Сбер не видит проблем у РЖД с обслуживанием долга почти на 3,5 трлн рублей. "
        "В банке говорят, что угрозы для обязательств компании нет.",
        '[{"channel": "@cb_economics"}]',
    )
    for label in ("Alpha Flow", "Market Pulse", "Closing Bell", "5-Minute Macro"):
        assert label not in html


def test_formatter_no_english_open_loop_by_default() -> None:
    html = format_public_post_html(
        "Сбер не видит проблем у РЖД с обслуживанием долга почти на 3,5 трлн рублей. "
        "В банке говорят, что угрозы для обязательств компании нет.",
        '[{"channel": "@cb_economics"}]',
    )
    for phrase in ("rally continues", "Traders now focus", "Watch closely", "risk-on continues"):
        assert phrase not in html


def test_formatter_no_irrelevant_ai_hashtag_on_debt_story() -> None:
    html = format_public_post_html(
        "Сбер не видит проблем у РЖД с обслуживанием долга почти на 3,5 трлн рублей. "
        "В банке говорят, что угрозы для обязательств компании нет.",
        '[{"channel": "@cb_economics"}]',
        include_cta=False,
    )
    assert "#AI" not in html


def test_formatter_no_redundant_hook_duplicating_headline() -> None:
    html = format_public_post_html(
        "ЦБ повысил ставку на 100 б.п. Это усиливает давление на кредитование.",
        '[{"channel": "@cb_economics"}]',
    )
    assert "Ключевой факт:" not in html
    assert "Главное для экономики:" not in html


def test_formatter_finishes_cut_off_thought() -> None:
    out = format_public_post_plain(
        "Сбер не видит проблем у РЖД. В банке говорят, что угрозы для обязательств компании нет:",
        '[{"channel": "@cb_economics"}]',
        include_cta=False,
    )
    assert ":…" not in out
    assert "нет:" not in out


def test_formatter_scrubs_json_from_body() -> None:
    body = "Заголовок\n\nТекст.\n\nИсточники (JSON)\n[{\"channel\": \"@x\"}]"
    out = format_public_post_plain(body, "[]")
    assert "JSON" not in out
    assert "channel" not in out


def test_formatter_adds_smart_hashtags_macro() -> None:
    out = format_public_post_plain(
        "Fed сохранила ставку, но инфляция остается выше целевого уровня.\n\n"
        "Рынок оценивает траекторию доходностей и влияние на доллар.",
        '[{"channel": "@cb_economics"}]',
        include_cta=False,
    )
    tags = re.findall(r"#\w+", out)
    assert any(t in tags for t in ("#Fed", "#Inflation", "#Rates", "#Macro"))
    assert len(tags) <= 3


def test_formatter_html_includes_hashtags_when_relevant() -> None:
    html = format_public_post_html(
        "NVIDIA поднимает прогноз, а рынок чипов ускоряет AI-капекс цикл.",
        '[{"channel": "@cb_economics"}]',
        include_cta=False,
    )
    assert "#AI" in html or "#NVIDIA" in html or "#Semiconductors" in html
