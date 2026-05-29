"""Tests for W1 floor eligibility scoring."""

from __future__ import annotations

from app.ops.floor_eligibility import evaluate_floor_eligibility

_SOURCES = '[{"channel": "@cb_economics"}]'


def test_floor_rejects_truncated() -> None:
    text = "Путин заявил, что газопровод через Армению будет построен для армянского."
    v = evaluate_floor_eligibility(text, sources_json=_SOURCES)
    assert not v.eligible
    assert v.reason == "truncated_mid_thought"


def test_floor_rejects_low_signal_bureaucratic() -> None:
    text = (
        "ФТС утвердила форму предписания о выезде транспорта с товарами за пределы РФ. "
        "Документ определяет шаблон."
    )
    v = evaluate_floor_eligibility(text, sources_json=_SOURCES)
    assert not v.eligible
    assert v.reason in {"premium_policy_failed", "low_informativeness", "floor_score_below_min"}


def test_floor_accepts_strong_geopolitics() -> None:
    text = (
        "Пашинян анонсировал строительство транзитного газопровода через территорию Армении. "
        "Премьер-министр заявил, что за транзит страна будет получать газ. "
        "Проект может усилить геополитическое давление на регион и повлиять на цены на энергоносители."
    )
    v = evaluate_floor_eligibility(text, sources_json=_SOURCES)
    assert v.eligible
    assert v.score >= 0.72
