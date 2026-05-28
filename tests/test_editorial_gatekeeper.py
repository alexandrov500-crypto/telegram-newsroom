from __future__ import annotations

from app.editorial.gatekeeper import (
    apply_gate_boost,
    editorial_gate,
    evaluate_editorial_gate,
    gate_filter_items,
)


def test_rejects_job_offer_meme():
    text = "Предложение работы от которого невозможно отказаться — смотри до конца"
    item = {"text": text, "source": "@cb_economics"}
    v = evaluate_editorial_gate(item)
    assert not v.allowed
    assert v.reason == "meme_or_joke"
    assert not editorial_gate(item)


def test_accepts_asml_geopolitics():
    text = (
        "ASML угрожает перенести производство из ЕС из-за новых регуляторных ограничений "
        "на экспорт оборудования"
    )
    item = {"text": text, "source": "@vedofon"}
    v = evaluate_editorial_gate(item)
    assert v.allowed
    assert editorial_gate(item)


def test_accepts_germany_lada_exit():
    text = "Germany: Lada exits the market amid new industrial policy requirements"
    item = {"text": text, "source": "@rbc_news"}
    assert editorial_gate(item)


def test_rejects_generic_fluff():
    text = "Мир уже не будет прежним, остаётся только наблюдать за событиями"
    item = {"text": text, "source": "@random"}
    assert not editorial_gate(item)


def test_gate_boost_with_numbers():
    text = "ЦБ повысил ключевую ставку на 1.5% по итогам заседания"
    item = {"text": text, "source": "@cb_economics", "final_score": 0.6}
    v = evaluate_editorial_gate(item)
    assert v.allowed
    boosted = apply_gate_boost(item, v)
    assert float(boosted["final_score"]) > 0.6


def test_gate_filter_list():
    items = [
        {"text": "лол мем невозможно отказаться", "source": "@x"},
        {"text": "Аэрофлот объявил о приватизации 25% акций государством", "source": "@cb"},
    ]
    out = gate_filter_items(items, runtime_dir="/tmp/gate_test", persist=False)
    assert len(out) == 1
    assert "Аэрофлот" in out[0]["text"]
