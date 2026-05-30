from __future__ import annotations

from pathlib import Path

from app.editorial.desk_filter import evaluate_desk_filter, persist_rejection
from app.editorial.scoring_engine import score_story


def test_rejects_incomplete_teaser():
    text = "Большие бюджеты в России в 2026 году выглядят так."
    escore = score_story(text=text, sources=["@cb_economics"])
    desk = evaluate_desk_filter(text, escore, sources=["@cb_economics"])
    assert not desk.publish
    assert desk.reason == "incomplete_teaser_no_body"


def test_rejects_unsafe_public_topic():
    text = (
        "Рынок эскорт-услуг вырос на 12% — аналитики обсуждают экономику проституции "
        "как отдельный сегмент."
    )
    escore = score_story(text=text, sources=["@decenter"])
    desk = evaluate_desk_filter(text, escore, sources=["@decenter"])
    assert not desk.publish
    assert desk.reason == "unsafe_public_topic"


def test_rejects_meme_content():
    text = "лол мем про крипту 😂🤣"
    escore = score_story(text=text, sources=["@decenter"])
    desk = evaluate_desk_filter(text, escore, sources=["@decenter"])
    assert not desk.publish
    assert desk.editorial_category in {"noise", "reject"}


def test_rejects_contractor_incident():
    text = "Подрядчик случайно отправил картинку заказчику вместо отчёта"
    escore = score_story(text=text, sources=["@decenter"])
    desk = evaluate_desk_filter(text, escore)
    assert not desk.publish
    assert "incident" in desk.reason or desk.editorial_category == "noise"


def test_includes_macro_news():
    text = (
        "Росстат: дефляция в России замедлилась в январе, "
        "индекс потребительских цен показал снижение давления."
    )
    escore = score_story(text=text, sources=["@cb_economics", "@tnews365"])
    desk = evaluate_desk_filter(text, escore, sources=["@cb_economics", "@tnews365"])
    assert desk.publish
    assert desk.editorial_category in {"macro", "market", "breaking"}
    assert desk.quality_score >= 30


def test_macro_floor_allows_moderate_score():
    text = (
        "Apple удалила из российского App Store 1213 приложений по требованию "
        "Роскомнадзора за 2025 год, говорится в отчёте компании."
    )
    escore = score_story(text=text, sources=["@cb_economics"])
    desk = evaluate_desk_filter(text, escore, sources=["@cb_economics"])
    assert desk.publish
    assert desk.reason in {
        "desk_priority_include",
        "desk_lower_priority_allow",
        "desk_macro_market_floor",
        "macro_high_signal",
    }


def test_breaking_override():
    text = "BREAKING: central bank emergency rate decision amid war escalation"
    escore = score_story(text=text, sources=["@cb_economics", "@tnews365"])
    desk = evaluate_desk_filter(text, escore, sources=["@cb_economics", "@tnews365"])
    assert desk.publish
    assert desk.breaking_override or desk.editorial_category == "breaking"


def test_rejects_bureaucratic_filler_without_market_implication():
    text = (
        "Приказом ФТС утверждена форма предписания о выезде транспортного средства с товарами "
        "за пределы территории Российской Федерации. Документ содержит порядок заполнения формы."
    )
    escore = score_story(text=text, sources=["@vedofon"])
    desk = evaluate_desk_filter(text, escore, sources=["@vedofon"])
    assert not desk.publish
    assert desk.reason == "bureaucratic_filler_low_signal"


def test_rejects_hidden_native_advertising():
    text = (
        "Партнерский материал: переходите по ссылке и получите скидку по промокоду MARKETS10. "
        "https://promo.example.com/?ref=affiliate"
    )
    escore = score_story(text=text, sources=["@cb_economics"])
    desk = evaluate_desk_filter(text, escore, sources=["@cb_economics"])
    assert not desk.publish
    assert desk.reason == "hidden_advertising_or_native_ad"


def test_rejects_premium_channel_native_ad():
    text = (
        "update → markets Strategy внесли 411.5 BTC ($30.3 млн) на Coinbase Prime — "
        "на Polymarket вероятность продажи до 31 декабря 2026 года достигла 84%. "
        "Ранее Сейлор дал понять, что компания будет продавать монеты время от… "
        "Полный разбор — в premium-канале. Почему это важно: Крипторынок реагирует "
        "на ликвидность и регуляторные сигналы быстрее традиционных активов."
    )
    escore = score_story(text=text, sources=["@DeCenter"])
    desk = evaluate_desk_filter(text, escore, sources=["@DeCenter"])
    assert not desk.publish
    assert desk.reason == "hidden_advertising_or_native_ad"


def test_persist_rejection_writes_jsonl(tmp_path: Path):
    text = "лол мем"
    escore = score_story(text=text, sources=["@decenter"])
    desk = evaluate_desk_filter(text, escore)
    persist_rejection(
        str(tmp_path / "rt"),
        article_id="abc",
        text_preview=text,
        decision=desk,
        sources=["@decenter"],
        escore=escore,
    )
    path = tmp_path / "rt" / "rejected_items.jsonl"
    assert path.is_file()
    assert "desk" in path.read_text(encoding="utf-8")
