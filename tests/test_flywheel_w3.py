"""W3 editorial identity + distribution flywheel unit tests."""

from __future__ import annotations

import tempfile
from types import SimpleNamespace

from app.flywheel.distribution_router import DistributionSurface, route_distribution_surface
from app.flywheel.explore_exploit import decide_explore_exploit
from app.flywheel.pipeline import enrich_for_publish, evaluate_pre_publish_editorial
from app.flywheel.retention_habit import active_habit_slot
from app.identity.differentiation import evaluate_differentiation, record_published_structure
from app.identity.identity_engine import evaluate_editorial_identity
from app.identity.insight_layer import extract_insight, score_insight_depth
from app.identity.style_guide import score_style_alignment


def _sample_macro_text() -> str:
    return (
        "ФРС сигнализирует о возможном снижении ключевой ставки на заседании в сентябре. "
        "Рынки переоценивают кривую доходности, а волатильность на индексах растёт. "
        "Инвесторы смещают позиции в защитные активы на фоне макро-неопределённости."
    )


def test_insight_layer_adds_why_it_matters() -> None:
    body = _sample_macro_text()
    result = extract_insight(body, vertical="macro")
    assert "Почему это важно" in result.text
    assert result.depth_score >= 0.5


def test_insight_layer_skips_generic_fallback_for_off_topic() -> None:
    body = (
        "В Китае набирают популярность рестораны для интровертов. "
        "Посетители сидят в отдельных маленьких кабинках, куда им приносят всю еду "
        "с минимальным контактом даже с сотрудниками."
    )
    result = extract_insight(body, vertical="general")
    assert "Почему это важно" not in result.text
    assert not result.has_insight


def test_style_alignment_rejects_generic_opener() -> None:
    generic = "По данным СМИ сообщается что рынки выросли сегодня утром."
    verdict = score_style_alignment(generic, vertical="macro")
    assert not verdict.aligned
    assert verdict.score < 0.58


def test_style_alignment_accepts_analytical_copy() -> None:
    enriched = extract_insight(_sample_macro_text(), vertical="macro").text
    verdict = score_style_alignment(enriched, vertical="macro")
    assert verdict.score >= 0.58


def test_differentiation_blocks_near_duplicate() -> None:
    text = enrich_for_publish(_sample_macro_text(), vertical="macro").content
    with tempfile.TemporaryDirectory() as td:
        record_published_structure(text, runtime_dir=td)
        verdict = evaluate_differentiation(text, runtime_dir=td)
        assert not verdict.unique
        assert verdict.reason == "near_duplicate_structure"


def test_distribution_router_discards_low_signal() -> None:
    settings = SimpleNamespace(target_channel_id=-1001)
    route = route_distribution_surface(
        settings,
        insight_score=0.35,
        style_score=0.5,
        signal_score=0.4,
    )
    assert route.surface == DistributionSurface.DISCARD


def test_distribution_router_high_signal_main_plus_digest() -> None:
    settings = SimpleNamespace(target_channel_id=-1001)
    route = route_distribution_surface(
        settings,
        insight_score=0.75,
        style_score=0.68,
        signal_score=0.7,
    )
    assert route.surface == DistributionSurface.MAIN
    assert route.also_digest


def test_editorial_identity_gate() -> None:
    with tempfile.TemporaryDirectory() as td:
        enriched = enrich_for_publish(_sample_macro_text(), vertical="macro").content
        verdict = evaluate_editorial_identity(enriched, runtime_dir=td, vertical="macro")
        assert verdict.allowed
        assert verdict.insight_score >= 0.45


def test_pre_publish_editorial_breaking_exempt() -> None:
    settings = SimpleNamespace(target_channel_id=-1001)
    with tempfile.TemporaryDirectory() as td:
        verdict = evaluate_pre_publish_editorial(
            "short",
            settings=settings,
            runtime_dir=td,
            is_breaking=True,
        )
        assert verdict.allowed
        assert verdict.reason == "breaking_exempt"


def test_explore_exploit_exploit_high_affinity() -> None:
    with tempfile.TemporaryDirectory() as td:
        decision = decide_explore_exploit(
            runtime_dir=td,
            topic_bucket="macro",
            novelty=0.55,
            cohort_affinity=0.6,
        )
        assert decision.mode == "exploit"
        assert decision.boost == 1.0


def test_insight_depth_scoring() -> None:
    shallow = "Краткая новость."
    deep = extract_insight(_sample_macro_text(), vertical="macro").text
    assert score_insight_depth(deep) > score_insight_depth(shallow)


def test_retention_habit_slot_returns_none_when_disabled(monkeypatch) -> None:
    monkeypatch.setenv("RETENTION_HABIT_ENABLED", "false")
    assert active_habit_slot("Europe/Moscow") is None
