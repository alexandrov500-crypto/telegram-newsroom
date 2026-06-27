"""Tests for Audience Unification Layer (AUH)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.editorial.audience_unification.auh_transformer import transform_for_unified_audience
from app.editorial.audience_unification.audience_compression_engine import compress_cluster_narrative
from app.editorial.audience_unification.communication_balance import evaluate_communication_balance
from app.editorial.audience_unification.controller import enrich_draft_with_auh
from app.editorial.audience_unification.cross_replacement_score import compute_crs
from app.editorial.audience_unification.reader_simulator import evaluate_reader_profile
from app.editorial.audience_unification.state import auh_distribution_snapshot, record_auh_evaluation
from app.editorial.audience_unification.unified_editorial_score import compute_ues
from app.editorial.audience_unification.unified_packaging import apply_unified_packaging
from app.editorial.audience_unification.universal_value_filter import evaluate_universal_value


@pytest.fixture(autouse=True)
def _enable_auh(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDITORIAL_AUDIENCE_UNIFICATION_LAYER", "true")


def test_reader_profile_multi_interest() -> None:
    text = (
        "Fed повысила ставку. Рынки отреагировали на NASDAQ. "
        "OpenAI анонсировала новую модель. Санкции усилили давление."
    )
    r = evaluate_reader_profile(text)
    assert r.cross_interest_breadth >= 3
    assert r.reader_relevance_score >= 60
    assert r.reader_unification_score >= 50


def test_transform_adds_implication_layers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSROOM_CLEAN_CHANNEL_COPY", "false")
    monkeypatch.setenv("NEWSROOM_CB_BRIEF_FORMAT", "false")
    body = "Компания X объявила о слиянии."
    out, meta = transform_for_unified_audience(body, matched_interests=("business",))
    assert meta["transformed"] is True
    assert "Почему это важно" in out
    assert "Что дальше" in out


def test_transform_explains_jargon(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NEWSROOM_CLEAN_CHANNEL_COPY", "false")
    monkeypatch.setenv("NEWSROOM_CB_BRIEF_FORMAT", "false")
    body = "Spread widened 15 b.p. after FOMC dot plot."
    out, meta = transform_for_unified_audience(body)
    assert "jargon_explained" in meta["rules_applied"] or "б.п." in out.lower()


def test_universal_value_rejects_niche_telegram() -> None:
    uv = evaluate_universal_value("Подписывайтесь на наш канал для полного разбора")
    assert uv.passes is False
    assert uv.reason == "niche_telegram_only"


def test_universal_value_downgrades_missing_impact() -> None:
    uv = evaluate_universal_value("Краткая заметка без контекста и объяснений", cross_interest_breadth=1)
    assert uv.downgrade_to_digest is True
    assert uv.reason == "missing_why_it_matters"


def test_crs_flagship_for_rich_post() -> None:
    text = (
        "Срочно: Fed повысила ставку на 50 b.p.\n\n"
        "Это важно: инфляция остаётся выше цели.\n\n"
        "Рынки NASDAQ и нефть отреагировали. OpenAI и tech-сектор в фокусе.\n\n"
        "Дальше ждём CPI и реакцию геополитики на санкции."
    )
    reader = evaluate_reader_profile(text)
    crs = compute_crs(
        text,
        cross_interest_breadth=reader.cross_interest_breadth,
        reader_clarity=reader.gender_neutral_clarity_score,
        quality_score=65.0,
        has_implication=True,
        cluster_size=2,
    )
    assert crs.total >= 50
    assert crs.tier in {"publish", "flagship", "digest"}


def test_ues_publish_immediately() -> None:
    ues = compute_ues(
        gravity_total=88.0,
        crs_total=82.0,
        reader_relevance=85.0,
        clarity=80.0,
        source_independence=0.9,
        crs_flagship=True,
    )
    assert ues.total >= 82
    assert ues.publish_immediately is True
    assert ues.reject is False


def test_ues_reject_in_core_mode() -> None:
    ues = compute_ues(
        gravity_total=30.0,
        crs_total=35.0,
        reader_relevance=40.0,
        clarity=45.0,
        source_independence=0.5,
        publishing_mode="core",
    )
    assert ues.reject is True
    assert ues.action == "reject"


def test_ues_stability_override_elastic_fill() -> None:
    ues = compute_ues(
        gravity_total=30.0,
        crs_total=35.0,
        reader_relevance=40.0,
        clarity=45.0,
        publishing_mode="elastic_fill",
    )
    assert ues.reject is False
    assert ues.force_digest is True


def test_communication_balance_flags_masculine_coded() -> None:
    bal = evaluate_communication_balance("Alpha male traders love this gamma squeeze bro")
    assert bal.passes is False
    assert "masculine_coded_framing" in bal.issues


def test_communication_balance_passes_neutral_analytical() -> None:
    text = (
        "Что происходит: ставка выросла.\n\n"
        "Почему важно: это влияет на решения инвесторов и бизнеса.\n\n"
        "Что дальше: следим за CPI."
    )
    bal = evaluate_communication_balance(text)
    assert bal.passes is True
    assert bal.clarity_index >= 70


def test_unified_packaging_adds_layers() -> None:
    body = "Fed raised rates unexpectedly."
    out, meta = apply_unified_packaging(body, flagship=True)
    assert meta["structure_applied"] is True
    assert "#MustRead" in out


def test_compression_merges_cluster() -> None:
    texts = [
        "Oil prices jumped on OPEC cut",
        "Energy stocks rallied in Europe",
        "Gas futures hit weekly high",
    ]
    out, meta = compress_cluster_narrative(texts, topic_hint="energy")
    assert meta["compressed"] is True
    assert meta["merged_signals"] >= 2
    assert "Единая картина" in out


def test_compression_single_passthrough() -> None:
    out, meta = compress_cluster_narrative(["Only one signal"])
    assert meta["compressed"] is False
    assert out == "Only one signal"


def test_enrich_draft_with_auh_returns_extras(tmp_path: Path) -> None:
    body = (
        "Fed повысила ставку на 50 b.p.\n\n"
        "Это важно: инфляция выше цели.\n\n"
        "Рынки NASDAQ отреагировали. OpenAI в фокусе.\n\n"
        "Дальше — данные CPI."
    )
    packaged, extras = enrich_draft_with_auh(
        body,
        runtime_dir=str(tmp_path),
        editorial_category="markets",
        quality_score=62.0,
        publishing_mode="core",
        cluster_size=2,
        dom_extras={
            "editorial_dominance": {
                "gravity": {"total": 75.0},
                "source_graph": {"independence_score": 0.8},
                "attention_design": {"has_implication": True},
            }
        },
    )
    assert "audience_unification" in extras
    auh = extras["audience_unification"]
    assert "ues" in auh
    assert "crs" in auh
    assert len(packaged) >= len(body)


def test_auh_state_distribution(tmp_path: Path) -> None:
    for ues in (78.0, 85.0, 62.0):
        record_auh_evaluation(
            str(tmp_path),
            ues=ues,
            crs=70.0,
            reader_relevance=72.0,
            published=ues >= 70,
        )
    snap = auh_distribution_snapshot(str(tmp_path))
    assert snap["evaluated_today"] == 3
    assert snap["published_today"] == 2
    assert snap["ues_avg"] > 0


def test_auh_disabled_returns_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EDITORIAL_AUDIENCE_UNIFICATION_LAYER", "false")
    body = "Short note."
    out, extras = enrich_draft_with_auh(
        body,
        runtime_dir=None,
        editorial_category="news",
        quality_score=50.0,
        publishing_mode="core",
    )
    assert out == body
    assert extras == {}
