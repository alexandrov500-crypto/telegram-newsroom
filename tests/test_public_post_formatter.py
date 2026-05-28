from __future__ import annotations

from app.editorial.public_post_formatter import format_public_post_plain
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


def test_formatter_default_no_cta() -> None:
    out = format_public_post_plain("Заголовок\n\nТекст новости.", '[{"channel": "@cb_economics"}]')
    assert "Подписывайтесь" not in out


def test_formatter_scrubs_json_from_body() -> None:
    body = "Заголовок\n\nТекст.\n\nИсточники (JSON)\n[{\"channel\": \"@x\"}]"
    out = format_public_post_plain(body, "[]")
    assert "JSON" not in out
    assert "channel" not in out
