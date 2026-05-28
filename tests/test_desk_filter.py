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
    escore = score_story(text=text, sources=["@cb_economics", "@vedofon"])
    desk = evaluate_desk_filter(text, escore, sources=["@cb_economics", "@vedofon"])
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
    escore = score_story(text=text, sources=["@cb_economics", "@vedofon"])
    desk = evaluate_desk_filter(text, escore, sources=["@cb_economics", "@vedofon"])
    assert desk.publish
    assert desk.breaking_override or desk.editorial_category == "breaking"


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
