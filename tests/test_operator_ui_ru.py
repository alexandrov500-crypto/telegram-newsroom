from __future__ import annotations

from publisher.operator_ui_ru import tr_reasoning_line, tr_scoring_reason


def test_tr_scoring_reason_by_code_and_english_label() -> None:
    assert "дубликат" in tr_scoring_reason("low_duplicate_overlap")
    assert "дубликат" in tr_scoring_reason("low duplicate overlap")
    assert "сходимость" in tr_scoring_reason("cross-source convergence")


def test_tr_reasoning_line() -> None:
    line = "urgency=0.40, novelty=1.00, dup_signal=0.10"
    out = tr_reasoning_line(line)
    assert "срочность=0.40" in out
    assert "новизна=1.00" in out
    assert "сигнал дубликата=0.10" in out
