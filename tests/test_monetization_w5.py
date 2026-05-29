"""W5 monetization layer unit tests."""

from __future__ import annotations

import tempfile

from app.monetization.ad_inventory import allocate_ad_slot, predict_ctr_rule_based
from app.monetization.audience_value import score_audience_value
from app.monetization.monetization_balance import evaluate_monetization_stress, record_publish_type
from app.monetization.premium_layer import classify_premium_content
from app.monetization.revenue_engine import RevenueStream, score_monetization_eligibility
from app.monetization.sponsor_injection import inject_sponsor_block, score_sponsor_safety


def _rich_body() -> str:
    return (
        "ФРС сигнализирует о снижении ставки — рынки переоценивают кривую доходности. "
        "Волатильность растёт, инвесторы смещают позиции в защитные активы. "
        "Почему это важно: изменение ставки перестраивает стоимость капитала и волатильность активов."
    )


def test_revenue_eligibility_high_signal() -> None:
    body = _rich_body()
    elig = score_monetization_eligibility(
        body,
        vertical="macro",
        insight_score=0.75,
        style_score=0.68,
        signal_score=0.7,
    )
    assert elig.score >= 0.48
    assert RevenueStream.SYNDICATION in elig.streams
    assert elig.sponsor_safe


def test_sponsor_safety_blocks_war_context() -> None:
    unsafe = "Эскалация войны привела к резкому росту геополитического риска."
    assert score_sponsor_safety(unsafe) < 0.62


def test_sponsor_injection_marks_partner_material() -> None:
    body = _rich_body()
    result = inject_sponsor_block(body, slot=None, vertical="macro")
    assert result.injected
    assert "партнёр" in result.content.lower()


def test_premium_classification_deep_content() -> None:
    body = _rich_body() + " Синтез: на следующей неделе ключевой фактор — решение по ставке."
    cls = classify_premium_content(body, insight_score=0.78, vertical="macro")
    assert cls.is_premium
    assert cls.tier in ("premium", "intel")


def test_ad_inventory_respects_daily_cap(monkeypatch) -> None:
    monkeypatch.setenv("W5_SPONSOR_MAX_DAILY", "1")
    with tempfile.TemporaryDirectory() as td:
        first = allocate_ad_slot(runtime_dir=td, topic_bucket="macro")
        assert first.allocate
        second = allocate_ad_slot(runtime_dir=td, topic_bucket="macro")
        assert not second.allocate
        assert second.reason == "daily_cap"


def test_monetization_balance_sponsor_overload() -> None:
    with tempfile.TemporaryDirectory() as td:
        for _ in range(8):
            record_publish_type(td, "sponsored")
        for _ in range(2):
            record_publish_type(td, "editorial")
        verdict = evaluate_monetization_stress(td)
        assert not verdict.allowed
        assert verdict.reason == "sponsor_overload"


def test_audience_value_scoring() -> None:
    with tempfile.TemporaryDirectory() as td:
        prof = score_audience_value(topic_bucket="macro", runtime_dir=td)
        assert 0.0 < prof.ltv_score <= 1.0
        assert 0.0 < prof.conversion_probability <= 1.0


def test_ctr_prediction_macro_boost() -> None:
    ctr = predict_ctr_rule_based(topic_bucket="macro_rates", narrative_phase="peak", hour_local=9)
    assert ctr >= 0.02
