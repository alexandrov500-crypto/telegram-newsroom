from __future__ import annotations

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
