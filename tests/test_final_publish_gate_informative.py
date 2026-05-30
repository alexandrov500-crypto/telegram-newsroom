from __future__ import annotations

import pytest

from app.editorial.content_quality import strip_public_template_metadata
from app.editorial.final_publish_gate import evaluate_final_publish_gate


def test_final_gate_blocks_incomplete_ellipsis_teaser() -> None:
    verdict = evaluate_final_publish_gate(
        content=(
            "Приказом ФТС утверждена форма предписания о выезде транспортного средства "
            "с находящимися в нем товарами за пределы территории Российской…"
        ),
        sources='[{"channel":"@vedofon"}]',
        operator_approved=False,
    )
    assert not verdict.allowed
    assert verdict.reason in {"incomplete_teaser_no_body", "incomplete_public_template"}


def test_final_gate_allows_complete_two_sentence_story() -> None:
    verdict = evaluate_final_publish_gate(
        content=(
            "ФТС утвердила форму предписания о выезде транспорта с товарами за пределы РФ. "
            "Новый регламент уточняет порядок контроля на границе и может усилить давление на логистику экспорта."
        ),
        sources='[{"channel":"@cb_economics"}]',
        operator_approved=False,
    )
    assert verdict.allowed or verdict.manual_review_required


def test_final_gate_blocks_low_signal_bureaucratic_filler() -> None:
    verdict = evaluate_final_publish_gate(
        content=(
            "Приказом ФТС утверждена форма предписания о выезде транспорта с товарами за пределы РФ. "
            "Документ определяет шаблон и порядок заполнения формы."
        ),
        sources='[{"channel":"@vedofon"}]',
        operator_approved=False,
    )
    assert not verdict.allowed
    assert verdict.reason in {"premium_policy_low_signal", "incomplete_public_template"}


def test_strip_public_template_metadata_removes_hashtags_and_footer() -> None:
    plain = (
        "Alpha Flow Сбер не видит проблем у РЖД с обслуживанием долга. "
        "В банке говорят, что угрозы для обязательств компании нет. "
        "Ключевой факт: Сбер не видит проблем у РЖД. "
        "AI rally continues: traders watch the next catalyst. "
        "Источник: @cb_economics #AI"
    )
    core = strip_public_template_metadata(plain)
    assert "#AI" not in core
    assert "Источник:" not in core
    assert "Alpha Flow" not in core
    assert core.endswith(".")


def test_final_gate_allows_complete_story_with_template_chrome() -> None:
    verdict = evaluate_final_publish_gate(
        content=(
            "ФТС утвердила форму предписания о выезде транспорта с товарами за пределы РФ. "
            "Новый регламент уточняет порядок контроля на границе и может усилить давление на логистику экспорта."
        ),
        sources='[{"channel":"@cb_economics"}]',
        operator_approved=False,
    )
    assert verdict.reason != "incomplete_public_template"
    assert verdict.allowed or verdict.manual_review_required


def test_final_gate_blocks_hidden_advertising() -> None:
    verdict = evaluate_final_publish_gate(
        content=(
            "Партнерский материал: используйте промокод NEWS10 и переходите по ссылке "
            "для получения скидки на тариф."
        ),
        sources='[{"channel":"@cb_economics"}]',
        operator_approved=False,
    )
    assert not verdict.allowed
    assert verdict.reason in {"hidden_advertising", "premium_policy_low_signal"}


def test_final_gate_blocks_premium_funnel_even_with_recovery_bypass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FORCE_PUBLISH_BYPASS", "true")
    verdict = evaluate_final_publish_gate(
        content=(
            "Жительница Калининграда поверила «криптоконсультанту» из мессенджера и потеряла "
            "6 300 000 рублей — при этом часть денег она заняла у… "
            "Полный разбор — в premium-канале."
        ),
        sources='[{"channel":"@DeCenter"}]',
        operator_approved=False,
    )
    assert not verdict.allowed
    assert verdict.reason == "hidden_advertising"


def test_final_gate_allows_ai_approved_autonomous_despite_publication_risk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AUTONOMOUS_EDITORIAL_MODE", "true")
    extras = (
        '{"ai_editorial_review": {"approved": true, "confidence": 0.68, "source": "rules", '
        '"reason": "rules_fallback_openai_error"}}'
    )
    verdict = evaluate_final_publish_gate(
        content=(
            "Минтранс подготовил проект приказа о реестре автоперевозчиков на платформе Гослог. "
            "С 2027 года данные о перевозчиках и транспорте будут вестись в электронной форме, "
            "что может изменить логистику и издержки грузоперевозок на рынке."
        ),
        sources='[{"channel":"@vedofon"}]',
        draft_extras_json=extras,
        operator_approved=False,
    )
    assert verdict.allowed, verdict.reason
